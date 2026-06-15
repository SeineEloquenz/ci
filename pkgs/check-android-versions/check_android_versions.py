#!/usr/bin/env python3
"""Check for Android SDK version updates and update shell.nix."""

import argparse
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

REPO_URL = "https://dl.google.com/android/repository/repository2-3.xml"


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def fetch_xml(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_revision(pkg):
    """
    Parse a package revision.

    Returns:
        (version_string, is_preview)
    """
    revision = None
    for child in pkg:
        if strip_ns(child.tag) == "revision":
            revision = child
            break

    if revision is None:
        return None, False

    parts = {}
    for elem in revision:
        tag = strip_ns(elem.tag)
        if elem.text and elem.text.strip():
            parts[tag] = elem.text.strip()

    major = parts.get("major", "0")
    minor = parts.get("minor", "0")
    micro = parts.get("micro", "0")
    version = f"{major}.{minor}.{micro}"

    preview = parts.get("preview")
    if preview is not None:
        return f"{version}-rc{preview}", True

    return version, False


def parse_repo(data: bytes):
    root = ET.fromstring(data)

    stable_id = "channel-0"
    for elem in root.iter():
        if strip_ns(elem.tag) == "channel":
            if elem.text and "stable" in elem.text.lower():
                stable_id = elem.get("id", "channel-0")
                break

    build_tools = []
    platforms = []

    for pkg in root.iter():
        if strip_ns(pkg.tag) != "remotePackage":
            continue

        path = pkg.get("path", "")
        channel_ref = None
        is_obsolete = False

        for child in pkg:
            tag = strip_ns(child.tag)
            if tag == "channelRef":
                channel_ref = child.get("ref")
            elif tag == "obsolete":
                is_obsolete = True

        if is_obsolete or channel_ref != stable_id:
            continue

        version, is_preview = parse_revision(pkg)
        if is_preview:
            continue

        if path.startswith("build-tools;"):
            if version:
                build_tools.append(version)
        elif re.match(r"^platforms;android-\d+$", path):
            platforms.append(int(path.split("android-")[1]))

    return build_tools, platforms


def version_key(v: str):
    return tuple(int(x) for x in v.split("."))


def set_github_output(name: str, value: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        delimiter = "GHADELIMITER"
        with open(github_output, "a") as f:
            f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"[output] {name}={value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for Android SDK version updates and update a shell file."
    )
    parser.add_argument(
        "shell_file",
        help="Path to the shell.nix file to update",
    )
    args = parser.parse_args()
    shell_path = args.shell_file

    print("Fetching Android SDK repository manifest...")
    data = fetch_xml(REPO_URL)
    build_tools, platforms = parse_repo(data)

    if not build_tools or not platforms:
        print("ERROR: failed to parse versions from repository XML", file=sys.stderr)
        return 1

    latest_bt = max(build_tools, key=version_key)
    latest_plat = str(max(platforms))

    print(f"Latest build-tools : {latest_bt}")
    print(f"Latest platform    : android-{latest_plat}")

    with open(shell_path) as f:
        shell = f.read()

    m_bt = re.search(r'buildToolsVersion\s*=\s*"([^"]+)"', shell)
    m_plat = re.search(r'platformVersions\s*=\s*\[\s*"([^"]+)"\s*\]', shell)

    if not m_bt or not m_plat:
        print(f"ERROR: could not parse current versions from {shell_path}", file=sys.stderr)
        return 1

    cur_bt = m_bt.group(1)
    cur_plat = m_plat.group(1)

    print(f"\nCurrent build-tools : {cur_bt}")
    print(f"Current platform    : android-{cur_plat}")

    changes = []

    if version_key(latest_bt) > version_key(cur_bt):
        changes.append(f"- build-tools: `{cur_bt}` → `{latest_bt}`")
        new_bt = latest_bt
    else:
        new_bt = cur_bt

    if int(latest_plat) > int(cur_plat):
        changes.append(f"- platform: `android-{cur_plat}` → `android-{latest_plat}`")
        new_plat = latest_plat
    else:
        new_plat = cur_plat

    if not changes:
        print("\nAll Android SDK versions are up to date.")
        set_github_output("updated", "false")
        return 0

    print("\nUpdates found:\n" + "\n".join(changes))

    updated = shell

    updated = re.sub(
        r'(buildToolsVersion\s*=\s*")[^"]+(")',
        rf"\g<1>{new_bt}\2",
        updated,
    )

    updated = re.sub(
        r'(platformVersions\s*=\s*\[)\s*"[^"]+"\s*(\])',
        rf'\g<1> "{new_plat}" \2',
        updated,
    )

    with open(shell_path, "w") as f:
        f.write(updated)

    print(f"{shell_path} updated.")

    pr_body = (
        f"Automated update of Android SDK versions in `{shell_path}`.\n\n"
        "## Changes\n\n"
        + "\n".join(changes)
    )

    set_github_output("updated", "true")
    set_github_output("pr_body", pr_body)

    return 0


if __name__ == "__main__":
    sys.exit(main())
