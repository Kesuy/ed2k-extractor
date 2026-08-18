# ED2K Extractor

一个 Windows 小工具，用于从 TXT、ZIP、RAR 中提取包含 `.mp4` 的 ED2K 链接。

## 功能

- 支持 `.txt`、`.zip`、`.rar`
- 支持把一个或多个 TXT / ZIP / RAR 直接拖到 EXE 上处理
- 双击 EXE 时自动扫描 EXE 所在目录的 TXT / ZIP / RAR
- ZIP / RAR 无需手动解压，直接读取压缩包内 TXT
- RAR 发布版内置完整 7-Zip 运行时，不依赖 Windows `tar.exe`
- 针对 RAR5、Unicode 文件名和 `.part1.rar` 分卷首卷处理
- TXT 编码兼容 UTF-8、GB18030/GBK、Big5、Shift-JIS/CP932
- 仅保留同时包含 `ed2k` 和 `.mp4` 的整行（大小写不敏感）
- ED2K 自动去重，并保留首次出现顺序
- 输出固定保存为 EXE 同目录的 `@ed2k.txt`

## 使用

### 方式 1：拖拽

把一个或多个 `.txt` / `.zip` / `.rar` 文件拖到 `ed2k-extractor.exe` 上。

### 方式 2：双击

把 `ed2k-extractor.exe` 放到待处理文件所在目录，双击运行。程序会扫描当前目录支持的文件。

## RAR 分卷

对于：

```text
abc.part1.rar
abc.part2.rar
abc.part3.rar
```

只需要处理 `abc.part1.rar`。如果一次把多个分卷都拖进去，程序会跳过 `part2` 及之后分卷，7-Zip 会自动从同目录读取后续卷。

## 关于密码压缩包

当前版本不会尝试猜测密码。遇到加密 TXT 时会在控制台提示读取失败，不会阻塞其他文件处理。

## 源码运行

源码模式需要本机安装 7-Zip 才能读取 RAR：

```powershell
python ed2k_extractor.py
```

## 本地打包

安装 Python 和 7-Zip 后运行：

```bat
build.bat
```

输出：

```text
dist\ed2k-extractor.exe
```

## Release

推送 `v*` 标签时，GitHub Actions 会自动构建 Windows 单文件 EXE，并上传到对应 GitHub Release。
