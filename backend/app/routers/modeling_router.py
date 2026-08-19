"""建模任务路由模块，提供任务创建、API 验证和配置管理等接口。"""

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from app.core.workflow import MathModelWorkFlow
from app.schemas.enums import CompTemplate, FormatOutPut
from app.utils.log_util import logger
from app.services.redis_manager import redis_manager
from app.schemas.request import Problem
from app.schemas.response import SystemMessage
from app.utils.common_utils import (
    create_task_id,
    create_work_dir,
    get_work_dir,
    get_current_files,
    md_2_docx,
)
import os
import json
import shutil
import asyncio
import uuid
from pathlib import Path
from typing import Dict, Tuple
from fastapi import HTTPException
from icecream import ic  # type: ignore[import-unresolved]
from app.schemas.request import ExampleRequest
from pydantic import BaseModel
from app.config.setting import settings, ApiType
from app.core.llm.providers.openai_chat import OpenAIChatProvider
from app.core.llm.providers.openai_responses import OpenAIResponsesProvider
from app.core.llm.providers.anthropic import AnthropicProvider
from app.core.llm.providers.base import BaseProvider
from app.core.workflow_state import (
    append_state_event,
    acquire_run_lock,
    get_resume_action,
    is_run_lock_active,
    load_task_registry,
    load_workflow_state,
    request_task_cancel,
    release_run_lock,
    update_task_registry,
)
import requests

router = APIRouter()

# 任务注册表: task_id -> (asyncio.Task, asyncio.Event)
_active_tasks: Dict[str, Tuple[asyncio.Task, asyncio.Event]] = {}


class ValidateApiKeyRequest(BaseModel):
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model_id: str
    api_type: str = "openai-chat"


class ValidateOpenalexEmailRequest(BaseModel):
    email: str


class ValidateOpenalexEmailResponse(BaseModel):
    valid: bool
    message: str


class ValidateApiKeyResponse(BaseModel):
    valid: bool
    message: str


class SaveApiConfigRequest(BaseModel):
    coordinator: dict
    modeler: dict
    coder: dict
    writer: dict
    openalex_email: str


@router.post("/save-api-config")
async def save_api_config(request: SaveApiConfigRequest):
    """
    保存验证成功的 API 配置到 settings
    """
    try:
        # 更新各个模块的设置
        if request.coordinator:
            settings.COORDINATOR_API_KEY = request.coordinator.get("apiKey", "")
            settings.COORDINATOR_MODEL = request.coordinator.get("modelId", "")
            settings.COORDINATOR_BASE_URL = request.coordinator.get("baseUrl", "")
            if api_type := request.coordinator.get("apiType"):
                settings.COORDINATOR_API_TYPE = api_type
            if cw := request.coordinator.get("contextWindow"):
                settings.COORDINATOR_CONTEXT_WINDOW = int(cw)

        if request.modeler:
            settings.MODELER_API_KEY = request.modeler.get("apiKey", "")
            settings.MODELER_MODEL = request.modeler.get("modelId", "")
            settings.MODELER_BASE_URL = request.modeler.get("baseUrl", "")
            if api_type := request.modeler.get("apiType"):
                settings.MODELER_API_TYPE = api_type
            if cw := request.modeler.get("contextWindow"):
                settings.MODELER_CONTEXT_WINDOW = int(cw)

        if request.coder:
            settings.CODER_API_KEY = request.coder.get("apiKey", "")
            settings.CODER_MODEL = request.coder.get("modelId", "")
            settings.CODER_BASE_URL = request.coder.get("baseUrl", "")
            if api_type := request.coder.get("apiType"):
                settings.CODER_API_TYPE = api_type
            if cw := request.coder.get("contextWindow"):
                settings.CODER_CONTEXT_WINDOW = int(cw)

        if request.writer:
            settings.WRITER_API_KEY = request.writer.get("apiKey", "")
            settings.WRITER_MODEL = request.writer.get("modelId", "")
            settings.WRITER_BASE_URL = request.writer.get("baseUrl", "")
            if api_type := request.writer.get("apiType"):
                settings.WRITER_API_TYPE = api_type
            if cw := request.writer.get("contextWindow"):
                settings.WRITER_CONTEXT_WINDOW = int(cw)

        if request.openalex_email:
            settings.OPENALEX_EMAIL = request.openalex_email

        return {"success": True, "message": "配置保存成功"}
    except Exception as e:
        logger.error(f"保存配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")


@router.post("/validate-api-key", response_model=ValidateApiKeyResponse)
async def validate_api_key(request: ValidateApiKeyRequest):
    """
    验证 API Key 的有效性
    """
    try:
        provider: BaseProvider
        match request.api_type:
            case ApiType.OPENAI_RESPONSES:
                provider = OpenAIResponsesProvider()
            case ApiType.ANTHROPIC:
                provider = AnthropicProvider()
            case _:
                provider = OpenAIChatProvider()

        await provider.call(
            messages=[{"role": "user", "content": "Hi"}],
            model=request.model_id,
            api_key=request.api_key,
            base_url=request.base_url
            if request.base_url != "https://api.openai.com/v1"
            else None,
            max_tokens=1,
        )

        return ValidateApiKeyResponse(valid=True, message="✓ 模型 API 验证成功")
    except Exception as e:
        error_msg = str(e)

        # 解析不同类型的错误
        if "401" in error_msg or "Unauthorized" in error_msg:
            return ValidateApiKeyResponse(valid=False, message="✗ API Key 无效或已过期")
        elif "404" in error_msg or "Not Found" in error_msg:
            return ValidateApiKeyResponse(
                valid=False, message="✗ 模型 ID 不存在或 Base URL 错误"
            )
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            return ValidateApiKeyResponse(
                valid=False, message="✗ 请求过于频繁，请稍后再试"
            )
        elif "403" in error_msg or "Forbidden" in error_msg:
            return ValidateApiKeyResponse(
                valid=False, message="✗ API 权限不足或账户余额不足"
            )
        else:
            return ValidateApiKeyResponse(
                valid=False, message=f"✗ 验证失败: {error_msg[:50]}..."
            )


@router.post("/validate-openalex-email", response_model=ValidateOpenalexEmailResponse)
async def validate_openalex_email(request: ValidateOpenalexEmailRequest):
    """
    验证 OpenAlex Email 的有效性
    """
    try:
        params = {"mailto": request.email}
        if settings.OPENALEX_API_KEY:
            params["api_key"] = settings.OPENALEX_API_KEY

        response = requests.get("https://api.openalex.org/works", params=params)
        logger.debug(f"OpenAlex Email 验证响应: {response}")
        response.raise_for_status()
        return ValidateOpenalexEmailResponse(
            valid=True, message="✓ OpenAlex Email 验证成功"
        )
    except Exception as e:
        return ValidateOpenalexEmailResponse(
            valid=False, message=f"✗ OpenAlex Email 验证失败: {str(e)}"
        )


@router.post("/example")
async def exampleModeling(
    example_request: ExampleRequest,
    background_tasks: BackgroundTasks,
):
    task_id = create_task_id()
    work_dir = create_work_dir(task_id)
    example_dir = os.path.join("app", "example", "example", example_request.source)
    ic(example_dir)
    with open(os.path.join(example_dir, "questions.txt"), "r", encoding="utf-8") as f:
        ques_all = f.read()

    current_files = get_current_files(example_dir, "data")
    for file in current_files:
        src_file = os.path.join(example_dir, file)
        dst_file = os.path.join(work_dir, file)
        with open(src_file, "rb") as src, open(dst_file, "wb") as dst:
            dst.write(src.read())
    # 存储任务ID
    await redis_manager.set(f"task_id:{task_id}", task_id)
    update_task_registry(work_dir, task_id=task_id, status="queued", cancel_requested=False)

    logger.info(f"Adding background task for task_id: {task_id}")
    # 将任务添加到后台执行
    background_tasks.add_task(
        run_modeling_task_async,
        task_id,
        ques_all,
        CompTemplate.CHINA,
        FormatOutPut.Markdown,
    )
    return {"task_id": task_id, "status": "processing"}


@router.post("/modeling")
async def modeling(
    background_tasks: BackgroundTasks,
    ques_all: str = Form(...),  # 从表单获取
    comp_template: CompTemplate = Form(...),  # 从表单获取
    format_output: FormatOutPut = Form(...),  # 从表单获取
    files: list[UploadFile] = File(default=None),
):
    task_id = create_task_id()
    work_dir = create_work_dir(task_id)

    # 如果有上传文件，保存文件
    if files:
        logger.info(f"开始处理上传的文件，工作目录: {work_dir}")
        for file in files:
            try:
                if not file.filename:
                    logger.warning("跳过空文件名")
                    continue
                safe_filename = Path(file.filename).name
                if safe_filename in {"", ".", ".."}:
                    logger.warning("跳过非法文件名")
                    continue
                data_file_path = os.path.abspath(os.path.join(work_dir, safe_filename))
                work_root = os.path.abspath(work_dir)
                if os.path.commonpath([data_file_path, work_root]) != work_root:
                    raise HTTPException(status_code=400, detail="非法文件路径")
                logger.info(f"保存文件: {file.filename} -> {data_file_path}")

                content = await file.read()
                if not content:
                    logger.warning(f"文件 {file.filename} 内容为空")
                    continue

                with open(data_file_path, "wb") as f:
                    f.write(content)
                logger.info(f"成功保存文件: {data_file_path}")

            except Exception as e:
                logger.error(f"保存文件 {file.filename} 失败: {str(e)}")
                raise HTTPException(
                    status_code=500, detail=f"保存文件 {file.filename} 失败: {str(e)}"
                )
    else:
        logger.warning("没有上传文件")

    # 存储任务ID
    await redis_manager.set(f"task_id:{task_id}", task_id)

    logger.info(f"Adding background task for task_id: {task_id}")
    # 将任务添加到后台执行
    update_task_registry(work_dir, task_id=task_id, status="queued", cancel_requested=False)
    background_tasks.add_task(
        run_modeling_task_async, task_id, ques_all, comp_template, format_output
    )
    return {"task_id": task_id, "status": "processing"}


async def run_modeling_task_async(
    task_id: str,
    ques_all: str,
    comp_template: CompTemplate,
    format_output: FormatOutPut,
    run_id: str | None = None,
):
    """异步执行建模任务。

    Args:
        task_id: 任务 ID。
        ques_all: 完整题目信息。
        comp_template: 竞赛模板类型。
        format_output: 输出格式。
    """
    logger.info(f"run modeling task for task_id: {task_id}")
    root_work_dir = get_work_dir(task_id)
    effective_run_id = run_id or "initial"
    if not acquire_run_lock(root_work_dir, effective_run_id):
        logger.warning("Task %s already has an active run", task_id)
        return

    update_task_registry(
        root_work_dir,
        task_id=task_id,
        run_id=effective_run_id,
        status="running",
        pid=os.getpid(),
        cancel_requested=False,
    )

    problem = Problem(
        task_id=task_id,
        ques_all=ques_all,
        comp_template=comp_template,
        format_output=format_output,
    )

    # 创建取消信号
    cancel_event = asyncio.Event()

    # 发送任务开始状态
    await redis_manager.publish_message(
        task_id,
        SystemMessage(content="任务开始处理"),
    )

    # 给一个短暂的延迟，确保 WebSocket 有机会连接
    await asyncio.sleep(1)

    # 创建工作流并传入取消事件
    workflow = MathModelWorkFlow()
    workflow.cancel_event = cancel_event

    # 创建任务并注册到全局表
    task = asyncio.create_task(workflow.execute(problem, run_id=run_id))
    _active_tasks[task_id] = (task, cancel_event)

    task_completed = False
    task_status = "failed"
    try:
        # 设置超时时间（5 小时）
        await asyncio.wait_for(task, timeout=3600 * 5)
        task_completed = True
        task_status = "completed"

        # 发送任务完成状态
        await redis_manager.publish_message(
            task_id,
            SystemMessage(content="任务处理完成", type="success"),
        )
    except asyncio.CancelledError:
        logger.info(f"任务 {task_id} 被取消")
        await redis_manager.publish_message(
            task_id,
            SystemMessage(content="任务已停止", type="warning"),
        )
    except Exception as e:
        logger.error(f"任务 {task_id} 执行失败: {e}")
        await redis_manager.publish_message(
            task_id,
            SystemMessage(content=f"任务执行失败: {str(e)}", type="error"),
        )
    finally:
        # 从注册表中清理
        _active_tasks.pop(task_id, None)
        final_registry = load_task_registry(root_work_dir) or {}
        if final_registry.get("cancel_requested"):
            task_status = "cancelled"
        update_task_registry(root_work_dir, status=task_status, cancel_requested=False)
        release_run_lock(root_work_dir, effective_run_id)
        # 仅在正常完成时转换 md 为 docx
        if task_completed:
            run_work_dir = getattr(workflow, "work_dir", None)
            root_work_dir = get_work_dir(task_id)
            if run_work_dir and os.path.abspath(run_work_dir) != os.path.abspath(root_work_dir):
                for filename in ("res.json", "res.md"):
                    source = os.path.join(run_work_dir, filename)
                    if os.path.exists(source):
                        shutil.copy2(source, os.path.join(root_work_dir, filename))
            md_2_docx(task_id)


class CancelTaskResponse(BaseModel):
    success: bool
    message: str


@router.post("/modeling/{task_id}/cancel", response_model=CancelTaskResponse)
async def cancel_task(task_id: str):
    """取消正在运行的任务。"""
    try:
        work_dir = get_work_dir(task_id)
    except FileNotFoundError:
        return CancelTaskResponse(success=False, message="task not found")
    registry = load_task_registry(work_dir)
    active_status = (
        registry
        and registry.get("status") in {"queued", "running", "retrying"}
        and is_run_lock_active(work_dir)
    )
    if task_id not in _active_tasks and not active_status:
        return CancelTaskResponse(
            success=False,
            message="任务不存在或已完成",
        )

    if task_id in _active_tasks:
        _, cancel_event = _active_tasks[task_id]
        cancel_event.set()
    request_task_cancel(work_dir)
    logger.info(f"已发送取消信号给任务 {task_id}")

    return CancelTaskResponse(
        success=True,
        message="停止指令已发送",
    )


@router.get("/modeling/{task_id}/status")
async def modeling_status(task_id: str):
    """Return the persisted workflow snapshot and the conservative resume action."""
    try:
        work_dir = get_work_dir(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    current_run_path = os.path.join(work_dir, "current_run.json")
    state_dir = work_dir
    current_run = None
    if os.path.exists(current_run_path):
        try:
            with open(current_run_path, "r", encoding="utf-8") as f:
                current_run = json.load(f)
            candidate_dir = current_run.get("work_dir") if isinstance(current_run, dict) else None
            if candidate_dir and os.path.isdir(candidate_dir):
                state_dir = candidate_dir
        except (OSError, json.JSONDecodeError):
            current_run = None

    state = load_workflow_state(state_dir)
    registry = load_task_registry(work_dir)
    events_path = os.path.join(state_dir, "workflow_events.json")
    events = []
    if os.path.exists(events_path):
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            events = payload if isinstance(payload, list) else []
        except (OSError, json.JSONDecodeError):
            events = []

    return {
        "task_id": task_id,
        "state": state,
        "run_id": current_run.get("run_id") if isinstance(current_run, dict) else "initial",
        "resume_action": get_resume_action(state_dir),
        "active": task_id in _active_tasks or bool(
            registry
            and registry.get("status") in {"queued", "running", "retrying"}
            and is_run_lock_active(work_dir)
        ),
        "task_registry": registry,
        "events": events,
    }


@router.post("/modeling/{task_id}/resume")
async def resume_modeling(task_id: str, background_tasks: BackgroundTasks):
    """Retry a persisted failed/cancelled workflow from its saved problem input."""
    if task_id in _active_tasks:
        raise HTTPException(status_code=409, detail="任务仍在运行")
    try:
        work_dir = get_work_dir(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    registry = load_task_registry(work_dir)
    if task_id in _active_tasks or (
        registry
        and registry.get("status") in {"queued", "running", "retrying"}
        and is_run_lock_active(work_dir)
    ):
        raise HTTPException(status_code=409, detail="task is already running")
    state = load_workflow_state(work_dir)
    if state is None or state.get("status") not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="当前任务不是可恢复的失败或取消状态")
    problem_path = os.path.join(work_dir, "problem.json")
    try:
        with open(problem_path, "r", encoding="utf-8") as f:
            problem = Problem.model_validate(json.load(f))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="任务缺少有效的 problem.json") from exc

    run_id = uuid.uuid4().hex
    append_state_event(work_dir, task_id, "workflow", "retrying", next_run_id=run_id)
    update_task_registry(work_dir, task_id=task_id, run_id=run_id, status="retrying", cancel_requested=False)
    background_tasks.add_task(
        run_modeling_task_async,
        task_id,
        problem.ques_all,
        problem.comp_template,
        problem.format_output,
        run_id,
    )
    return {"task_id": task_id, "status": "retrying", "resume_action": "retry_workflow"}
