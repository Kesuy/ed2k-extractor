import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

APP_NAME = "ED2K Extractor"
VERSION = "1.0.0"
OUTPUT_NAME = "@ed2k.txt"
SUPPORTED_EXTS = {".txt", ".zip", ".rar"}


def app_dir() -> Path:
    """源码运行时返回脚本目录；PyInstaller EXE 运行时返回 EXE 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_dir() -> Path:
    """PyInstaller onefile 解包资源目录；源码运行时返回脚本目录。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def decode_text(data: bytes) -> str:
    """尽量兼容常见中日韩 TXT 编码。"""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "shift_jis", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def extract_ed2k_lines_from_text(text: str) -> list[str]:
    """保留原脚本规则：仅提取同时包含 ed2k 和 .mp4 的整行，大小写不敏感。"""
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if "ed2k" in lower and ".mp4" in lower:
            result.append(stripped)
    return result


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def print_found(source_type: str, source_name: str, inner_name: str | None, links: list[str]) -> None:
    if inner_name:
        print(f"\n[{source_type}] {source_name}")
        print(f"  └─ {inner_name}：找到 {len(links)} 条")
    else:
        print(f"\n[{source_type}] {source_name}：找到 {len(links)} 条")

    for link in links:
        print(f"     {link}")


def process_txt(file_path: Path) -> tuple[list[str], int, int]:
    try:
        links = extract_ed2k_lines_from_text(decode_text(file_path.read_bytes()))
        print_found("TXT", str(file_path), None, links)
        return links, 1, 0
    except Exception as exc:
        print(f"\n[TXT] 读取失败：{file_path}")
        print(f"      {exc}")
        return [], 0, 1


def process_zip(file_path: Path) -> tuple[list[str], int, int]:
    all_links = []
    txt_count = 0
    failed_count = 0

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            txt_members = [
                info for info in zf.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".txt")
            ]

            if not txt_members:
                print(f"\n[ZIP] {file_path}：压缩包内没有 TXT")
                return [], 0, 0

            for info in txt_members:
                try:
                    data = zf.read(info)
                    links = extract_ed2k_lines_from_text(decode_text(data))
                    print_found("ZIP", str(file_path), info.filename, links)
                    all_links.extend(links)
                    txt_count += 1
                except RuntimeError as exc:
                    print(f"\n[ZIP] 无法读取：{file_path} -> {info.filename}")
                    print(f"      可能是加密文件：{exc}")
                    failed_count += 1
                except Exception as exc:
                    print(f"\n[ZIP] 读取失败：{file_path} -> {info.filename}")
                    print(f"      {exc}")
                    failed_count += 1

    except zipfile.BadZipFile:
        print(f"\n[ZIP] 文件损坏或不是有效 ZIP：{file_path}")
        failed_count += 1
    except Exception as exc:
        print(f"\n[ZIP] 打开失败：{file_path}")
        print(f"      {exc}")
        failed_count += 1

    return all_links, txt_count, failed_count


def find_executable(names: tuple[str, ...], extra_paths: tuple[str, ...] = ()) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    for path in extra_paths:
        if os.path.isfile(path):
            return path

    return None


def get_7zip() -> str | None:
    """
    优先使用打包进 EXE 的 7z.exe，其次使用系统已安装的 7-Zip。
    不再使用 Windows tar.exe 作为 RAR 后端，避免 RAR5/Unicode/多卷兼容问题。
    """
    bundled = bundled_dir() / "7z.exe"
    if bundled.is_file():
        return str(bundled)

    return find_executable(
        ("7z", "7zz", "7za"),
        (
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ),
    )


def run_command_bytes(args: list[str]) -> tuple[int, bytes, bytes]:
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def list_archive_txt_7z(exe: str, archive: Path) -> list[str]:
    code, out, err = run_command_bytes([exe, "l", "-slt", "-ba", "-p-", str(archive)])
    if code not in (0, 1):
        raise RuntimeError(decode_text(err or out).strip() or f"7-Zip 返回代码 {code}")

    text = decode_text(out).replace("\r\n", "\n")
    members = []

    for block in re.split(r"\n\s*\n", text):
        props = {}
        for line in block.splitlines():
            if " = " in line:
                key, value = line.split(" = ", 1)
                props[key.strip()] = value.strip()

        member = props.get("Path")
        folder = props.get("Folder")
        attributes = props.get("Attributes", "")
        is_folder = folder == "+" or attributes.startswith("D")

        if member and not is_folder and member.lower().endswith(".txt"):
            members.append(member)

    if not members:
        for line in text.splitlines():
            if line.startswith("Path = "):
                member = line[7:].strip()
                if member.lower().endswith(".txt"):
                    members.append(member)

    return dedupe_keep_order(members)


def read_archive_member_7z(exe: str, archive: Path, member: str) -> bytes:
    code, out, err = run_command_bytes([exe, "x", "-so", "-y", "-p-", str(archive), member])
    if code not in (0, 1):
        message = decode_text(err or out).strip()
        if "Wrong password" in message or "password" in message.lower():
            raise RuntimeError("压缩包需要密码，当前未提供密码")
        raise RuntimeError(message or f"7-Zip 返回代码 {code}")
    return out


def is_non_first_rar_volume(path: Path) -> bool:
    """避免一次拖入整套分卷时重复扫描 part2/part3；第一卷仍正常处理。"""
    name = path.name.lower()
    match = re.search(r"\.part(\d+)\.rar$", name)
    return bool(match and int(match.group(1)) > 1)


def process_rar(file_path: Path) -> tuple[list[str], int, int]:
    all_links = []
    txt_count = 0
    failed_count = 0

    if is_non_first_rar_volume(file_path):
        print(f"\n[RAR] 跳过非首分卷：{file_path.name}")
        print("      请处理 .part1.rar；7-Zip 会自动读取同目录后续分卷。")
        return [], 0, 0

    exe = get_7zip()
    if not exe:
        print(f"\n[RAR] 无法处理：{file_path}")
        print("      未找到可用的 7-Zip。")
        print("      EXE 发布版会自带 7-Zip；源码运行请安装 7-Zip。")
        return [], 0, 1

    try:
        members = list_archive_txt_7z(exe, file_path)
        if not members:
            print(f"\n[RAR] {file_path}：压缩包内没有 TXT，或文件需要密码")
            return [], 0, 0

        for member in members:
            try:
                data = read_archive_member_7z(exe, file_path, member)
                links = extract_ed2k_lines_from_text(decode_text(data))
                print_found("RAR", str(file_path), member, links)
                all_links.extend(links)
                txt_count += 1
            except Exception as exc:
                print(f"\n[RAR] 读取失败：{file_path} -> {member}")
                print(f"      {exc}")
                failed_count += 1

    except Exception as exc:
        print(f"\n[RAR] 打开失败：{file_path}")
        print(f"      7-Zip：{exe}")
        print(f"      {exc}")
        failed_count += 1

    return all_links, txt_count, failed_count


def collect_default_files(base_dir: Path) -> list[Path]:
    files = []
    for item in base_dir.iterdir():
        if not item.is_file():
            continue
        if item.name.lower() == OUTPUT_NAME.lower():
            continue
        if item.suffix.lower() in SUPPORTED_EXTS:
            files.append(item)
    return sorted(files, key=lambda p: p.name.lower())


def collect_dragged_files(args: list[str]) -> list[Path]:
    files = []
    for arg in args:
        path = Path(arg).expanduser()

        if not path.exists():
            print(f"[跳过] 文件不存在：{path}")
            continue
        if not path.is_file():
            print(f"[跳过] 不是文件：{path}")
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS:
            print(f"[跳过] 不支持的格式：{path}")
            continue
        if path.name.lower() == OUTPUT_NAME.lower():
            print(f"[跳过] 输出文件本身：{path}")
            continue

        files.append(path)

    return files


def main() -> None:
    base_dir = app_dir()

    if len(sys.argv) > 1:
        input_files = collect_dragged_files(sys.argv[1:])
        mode = "拖拽模式"
    else:
        input_files = collect_default_files(base_dir)
        mode = "目录扫描模式"

    print("=" * 72)
    print(f"{APP_NAME} v{VERSION} - {mode}")
    print("支持：TXT / ZIP / RAR（含 RAR5、Unicode 文件名、RAR 分卷首卷）")
    print("规则：提取同时包含 ed2k 和 .mp4 的行；最终自动去重")
    print("=" * 72)

    if not input_files:
        print("\n没有找到可处理的 TXT / ZIP / RAR 文件。")
        return

    print("\n待处理文件：")
    for path in input_files:
        print(f"  - {path}")

    all_links = []
    txt_count = 0
    failed_count = 0
    file_counts = {".txt": 0, ".zip": 0, ".rar": 0}

    for file_path in input_files:
        ext = file_path.suffix.lower()
        file_counts[ext] += 1

        if ext == ".txt":
            links, txts, failed = process_txt(file_path)
        elif ext == ".zip":
            links, txts, failed = process_zip(file_path)
        else:
            links, txts, failed = process_rar(file_path)

        all_links.extend(links)
        txt_count += txts
        failed_count += failed

    unique_links = dedupe_keep_order(all_links)
    duplicate_count = len(all_links) - len(unique_links)
    output = base_dir / OUTPUT_NAME

    try:
        with output.open("w", encoding="utf-8-sig", newline="\n") as f:
            for line in unique_links:
                f.write(line + "\n")
    except Exception as exc:
        print(f"\n写入输出文件失败：{output}")
        print(exc)
        return

    print("\n" + "=" * 72)
    print("扫描统计")
    print(f"  TXT 文件：{file_counts['.txt']}")
    print(f"  ZIP 文件：{file_counts['.zip']}")
    print(f"  RAR 文件：{file_counts['.rar']}")
    print(f"  实际读取 TXT：{txt_count}")
    print(f"  原始 ED2K：{len(all_links)}")
    print(f"  去重后 ED2K：{len(unique_links)}")
    print(f"  去除重复：{duplicate_count}")
    print(f"  读取失败：{failed_count}")
    print(f"  输出文件：{output}")
    print("=" * 72)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户取消。")
    except Exception as exc:
        print("\n程序发生未处理异常：")
        print(exc)
    finally:
        try:
            input("\n按回车退出...")
        except EOFError:
            pass
