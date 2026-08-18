# 结构化文献协议

文献搜索由当前 Harness 的 WebSearch/WebFetch 完成，本地工具负责登记、去重、校验、导出和验收。不依赖旧 Web 后端的 OpenAlex Agent。

## 登记文件

统一维护：

```text
data/literature.json
```

初始化：

```bash
python "<项目根>/backend/scripts/literature_registry.py" init
```

## 搜索与核验

1. 根据模型、关键假设和数据来源生成检索词。
2. 优先核对 DOI 页面、出版社、期刊、会议或可信学术索引。
3. 记录真实作者、题名、年份、期刊/会议、DOI 或稳定 URL。
4. `verified` 必须登记至少一个实际查看过的核验来源。
5. 历史案例卡只能提示检索方向，不能自动变成论文参考文献。

登记示例：

```bash
python "<项目根>/backend/scripts/literature_registry.py" add \
  --id ref1 \
  --title "<真实题名>" \
  --authors "Author A;Author B" \
  --year 2024 \
  --venue "<期刊或会议>" \
  --doi "10.xxxx/xxxx" \
  --verified-source "DOI landing page" \
  --used-in "模型建立" \
  --verification-status verified
```

## 引用纪律

- 同一文献只在参考文献表登记一次，但可以在正文多个必要位置复用同一引用键。
- 不得为满足数量要求添加与正文无关的文献。
- 文献不能替代本题推导；引用只支撑模型来源、参数范围、假设或对比依据。
- 没有核验成功的文献保持 `unverified`，不得进入最终参考文献文件。

## 校验与导出

```bash
python "<项目根>/backend/scripts/literature_registry.py" validate
python "<项目根>/backend/scripts/literature_registry.py" export --format typst --output paper/references.typ
python "<项目根>/backend/scripts/literature_registry.py" export --format latex --output paper/references.tex
```

导出前会检查重复 ID/DOI、作者、年份、DOI/URL、核验来源和正文用途。最终引用语法仍按所选论文模板调整。
