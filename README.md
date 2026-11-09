# S2action

在 GitHub Actions 的 macOS / Xcode Runner 上调用上游 [S2Arm](https://github.com/jhaizhou-ops/S2Arm)，构建 iOS 游戏资源包。

本仓库只保存 CI 工作流和辅助脚本，不保存 S2Arm 源码、游戏文件、`prod.keys` 或生成的资源包。

## 输入配置

在仓库 **Settings → Secrets and variables → Actions → New repository secret** 中添加：

| Secret 名称 | 内容 |
|---|---|
| `GAME_URLS` | 每行一个可直接下载文件的 HTTP(S) URL。支持 NSP、XCI、NSZ、XCZ、NUP；本体、更新和 DLC 分别填写。 |
| `PROD_KEYS_B64` | 自己的 `prod.keys` 文件经过 Base64 编码后的完整文本。 |

Windows PowerShell 可用下面的命令生成 Base64（只复制输出，不要把密钥文件提交到仓库）：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\to\prod.keys"))
```

下载地址必须能由 Runner 直接通过 HTTP(S) 获取文件。需要登录 Cookie、百度网盘客户端授权或网页二次跳转的分享链接，不能直接当作下载 URL；这类来源需要单独适配下载器。

## 运行

1. 打开 **Actions → Build S2Arm game resource pack → Run workflow**。
2. `s2arm_ref` 默认是上游 `main`，也可以指定上游分支或标签。
3. 如果输入目录里包含多个本体，可填写 `title_id`（16 位十六进制程序号）。
4. `game_name` 可选，只允许字母、数字、下划线和连字符。
5. 默认不上传 Artifact。只有明确接受资源包对公开仓库读者可下载时，才勾选 `upload_artifact`。

工作流调用上游 `pack/oneclick/oneclick.sh` 的 iOS 构建路径，因为上游当前通过该路径生成并交付资源包；IPA 仅作为上游流程的中间产物，验证资源包后会删除 IPA、解包目录和私有产物根以回收 Runner 磁盘空间。

## 安全说明

- 本仓库是 Public。不要提交游戏文件、密钥、带访问令牌的下载链接或生成的资源包。
- `GAME_URLS` 和 `PROD_KEYS_B64` 必须使用 GitHub Actions Secrets，不要写入 workflow 的明文输入或日志。
- 公开仓库的 Actions Artifact 不应承载不准备公开分发的游戏资源；上传开关默认关闭。
- Runner 结束后会销毁临时下载目录和密钥文件；资源包只会在明确启用 Artifact 上传时作为构建产物保留。

## 上游

- [S2Arm](https://github.com/jhaizhou-ops/S2Arm)
- [上游一键出包脚本](https://github.com/jhaizhou-ops/S2Arm/blob/main/pack/oneclick/oneclick.sh)
- [上游资源包格式与核对工具](https://github.com/jhaizhou-ops/S2Arm/tree/main/pack)
