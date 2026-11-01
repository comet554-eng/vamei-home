# 医疗器械出海销售支持与供应协同工作台

这是一个可直接打开的前端 MVP 原型，覆盖：

- 业务总览：客户、回访、合同提醒、库存缺口
- 客户与回访：客户资产表、搜索、分级、手动新增
- 上新素材库：产品参数转英文上架方案
- 合规资料库：客户需求清单与资料匹配结果
- 采购与库存：需求预测、缺口计算、备货建议

## 运行

在本目录启动一个静态服务：

```powershell
python -m http.server 4173
```

然后打开 `http://localhost:4173`。

原型当前使用演示数据，后续可以将 `app.js` 中的 `state` 和各个动作函数替换为真实 API。

## 和队友版本的关系（2026-11-01）

本目录来自队友的「MedBridge工作台源码.zip」里的 `public/medbridge/`，包括 calm.css、通知中心、产品资料导入和网页机器人。以下文件和队友版一字不差：`app.js`、`styles.css`、`calm.css`、`product-import.js`、`widget/`。

`index.html` 在队友版的基础上只加了四处，没有删任何内容：

1. 在 `calm.css` 后面引入 `inquiry.css`。
2. 左侧导航加了「询盘助手」。
3. 加了 `#view-inquiry` 页面。
4. 引入 `inquiry.js`。

「询盘助手」页、网页机器人的 AI 模式和产品资料导入都要后端：在项目根目录运行 `python app/server.py`，然后打开 http://127.0.0.1:8766/ 。详见上一级目录的 README。
