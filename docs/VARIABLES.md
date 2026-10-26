# 配置与秘密边界

本页仅记录变量名和来源，不包含真实值。开发时沿用本地配置，不为准备工作读取、复制或轮换密钥。完整环境运行见 [LOCAL-RUN.md](../LOCAL-RUN.md)。

| 名称 | 使用方和作用域 | 来源 | 轮换/变更方式 | 主要风险 |
| --- | --- | --- | --- | --- |
| DATABASE_URL | server Prisma | server/.env | 更换独立数据库账号并验证连接 | 不输出连接串；不把共享业务库用于试验 |
| JWT_SECRET | server auth/middleware.ts | server/.env | 服务器重启并重新登录 | 至少 32 字符；轮换使旧 JWT 失效 |
| HOST / PORT | server index.ts | server/.env | 修改后重启本项目 | 当前本地要求 127.0.0.1:3001；代码默认监听所有网卡 |
| YIBIAO_DATA_DIR | server document/paths.ts | 环境或当前工作目录/data | 移动前同时备份 DB 和文件，测试恢复 | DATA_DIR 不是这里读取的变量名；不得据旧注释误设 |
| VITE_API_BASE_URL | client http.ts / sse.ts | client/.env，构建期 | 改值后重启或重建前端 | VITE 前缀会进入浏览器；不得承载秘密 |
| VITE_SOURCE_REPOSITORY_URL | client 源码归属入口 | client/.env，构建期 | 改为实际修改版来源 | 保持源码归属与发布内容一致 |
| POSTGRES_USER / POSTGRES_DB / POSTGRES_PASSWORD | 本地 PostgreSQL 容器 | .env.postgres.local | 使用数据库管理操作轮换；改 env 不等于改既有卷密码 | 不输出或打包该文件 |
| text_model_profiles.*.api_key 等 | server AI + 管理员设置页面 | AppConfig JSON / 数据库 | 管理员设置中更新并撤销旧 key | 不是只存在环境变量；数据库备份同样敏感 |
| model_name / base_url / text_model_provider | server config/store.ts、ai/service.ts | AppConfig 合并 UserConfig | 平台设置 | 外发目的地和模型成本边界；不能静默替换模型 |
| YIBIAO_AGENT_RUNTIME | server index.ts | 环境，默认 pi | 重启本项目 | 选择既有 Agent 能力；复核首版拟不用工具型 Agent |
| YIBIAO_OPENCODE_BIN | 可选 opencode runtime | 环境 | 管理员检查受信任本地路径 | 不从文档或普通用户参数接收可执行路径 |
| AI_TEXT_CONCURRENCY_LIMIT / AI_TEXT_QUEUE_LIMIT | AI 队列及配置归一化 | server 环境 | 依据模型配额调整 | 限制并发不等于限制总费用；具体上限语义以 normalize.ts 为准 |
| AI_PROMPT_CACHE_WARMUP_MS | 既有生成流程 | server 环境 | 依 runner 语义调整 | 不应成为新增复核自动外发的理由 |

## 浏览器中的秘密

检查的 client/.env.example 仅有公开 API/源码地址，未见打包 AI key 的环境变量设计；本次未搜索真实密钥值，也没有做发布产物秘密扫描。不能据此声称秘密泄露绝不可能。

当前 GET /api/config 对普通用户脱敏，对管理员返回完整配置。因此“密钥只在服务端，任何浏览器都拿不到”不是现有代码事实。管理员浏览器、localStorage 中的正式访问令牌和数据库备份都需要保护。初始改密受限令牌按现有流程仅用于改密，禁止放 URL 或日志。

新增复核模块只读取调用所需的服务端配置，不把 config 对象或真实 key 放进结果、SSE、日志、inputSignature、导出或文档。

## 资料与日志

- 原始 DOCX、结构索引、模型输入片段和模型失败响应都可能包含标书内容，过滤 API key 不等于对商业信息完成脱敏。
- 现有 ai-diagnostics 会保存部分失败响应，配置为最多 60 KB 文本、七天清理；只适用于诊断文件，不代表所有上传文件都有七天删除策略。
- Mermaid 导出链路可将图表内容编码后发给 mermaid.ink。新增复核报告拟不依赖该外部渲染链路。
- 未确认客户出网权限前，使用虚构样例；真实模型验收应另行记录提供商、输入范围、费用授权和保存政策。

## 真实资料试点前

1. 完成管理员首次改密，确认仅本地或受控内网访问。
2. 核实模型是否需要外发数据，获得业务方许可；没有模型时显示能力缺失。
3. 测试项目及子资源权限、下载路径边界、任务和事件数据范围。
4. 确定原文件、复核记录和诊断数据的保留/删除方式，验证备份恢复。
5. 公网服务另做 HTTPS、CORS 来源限制、访问控制和租户边界验收。
6. 对此前 Codex 会话日志告警完成独立复核；源码目录扫描未检出不能替代该步骤。

这些是后续试点条件，本次准备没有更改安全设置、读取凭据或运行付费模型。
