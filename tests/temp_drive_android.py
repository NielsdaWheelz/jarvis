"""Controlled Android UI proof against the ordinary home routes."""

import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

ADB = ["/Users/nnandal/Library/Android/sdk/platform-tools/adb", "-s", "emulator-5582"]
HOST = "http://127.0.0.1:63817"
PACKAGE = "dev.niels.jarvis.drivefixture"
MAIN = "dev.niels.jarvis.MainActivity"
ARCHIVE = "/f/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?page=6"


def adb(*args):
    return subprocess.check_output([*ADB, *args], text=True, timeout=18)


def ui():
    xml = adb("exec-out", "uiautomator", "dump", "/dev/tty").split("UI hierchary")[0]
    return ET.fromstring(xml).iter("node")


def present(label):
    for _ in range(4):
        nodes = list(ui())
        for node in nodes:
            actual = node.get("text") or node.get("content-desc") or ""
            if actual == label:
                return node
    raise AssertionError((label, [item.get("text") or item.get("content-desc") for item in nodes]))


def tap(label):
    node = present(label)
    x, y, a, b = map(int, re.findall(r"\d+", node.get("bounds")))
    adb("shell", "input", "tap", str((x + a)//2), str((y + b)//2))


def show(path):
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", HOST + path, "-n", PACKAGE + "/" + MAIN)


def fixture(state):
    with urllib.request.urlopen(HOST + "/fixture/state/" + state, timeout=5) as stream:
        assert stream.status == 200


def cache():
    return adb("shell", "run-as", PACKAGE, "ls", "cache/verified").strip()


fixture("normal")
show("/files")
present("my drive")
present("pending uploads")
tap("upload.pdf")
present("download")
adb("shell", "input", "keyevent", "4")
tap("tax")
tap("2026")
present("return.pdf")
show(ARCHIVE)
present("page 6 of 6")
assert cache().endswith(".preview"), cache()
adb("shell", "input", "keyevent", "4")
present("return.pdf")
assert cache() == "", cache()
fixture("changed")
show(ARCHIVE)
present("page 6 is unavailable in this file.")
tap("open page 1")
present("page 1 of 5")
fixture("denied")
show("/files/owner/return")
present("this file is missing or you no longer have access.")
fixture("normal")
show("/files/owner/image")
present("image preview")
show("/files/owner/letter")
present("open in drive")
show("/files")
tap("recent")
present("pdf · tax / 2026")
present("pdf · shared / accountant")
tap("more files")
present("google drive is limiting requests. retry in 1 seconds.")
present("return.pdf")
# A new process removes a stale copy before showing any preview.
adb("shell", "am", "force-stop", PACKAGE)
adb("shell", "run-as", PACKAGE, "touch", "cache/verified/stale.preview")
show("/files")
present("my drive")
assert not adb("shell", "run-as", PACKAGE, "find", "cache", "-name", "*.preview").strip()
print("controlled android routes, old citation, page 6, changed page, raster, docs, duplicate location, quota preservation and cleanup: pass")
