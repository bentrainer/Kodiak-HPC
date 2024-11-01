#!/usr/bin/env python3
# coding: utf-8
import os
import re
import sys

from bs4 import BeautifulSoup as bs
import requests

__target__  = "linux"
__install__ = "offline"

if __name__ == "__main__":

    argv = sys.argv
    while argv and ("python" in argv[0].lower() or ".py" in argv[0].lower()):
        argv = argv[1:]
    fn = os.path.join("setup_scripts", "0_oneMKL.sh") if not argv else argv[0]

    with open(fn, encoding="utf-8") as f:
        script = f.read()

    try:
        old_url = re.search(r"https.*?sh", script).group(0)

        soup = bs(requests.get(f"https://www.intel.com/content/www/us/en/developer/tools/oneapi/onemkl-download.html?operatingsystem={__target__}&{__target__}-install={__install__}").content, "html5lib")

        code = soup.find("code", attrs={"class": "language-bash"}).text
        url  = re.search(r"https.*?sh", code).group(0)
    except Exception as e:
        print(e)
    else:
        if old_url!=url:
            # print(f"update \"{old_url}\" -> \"{url}\"")
            with open(fn, "w", encoding="utf-8") as f:
                f.write(script.replace(old_url, url))

            try:
                version = re.search(r"\d+\..*\d+(?=_offline)", url).group(0)
                print(f"update mkl to {version}", end="")
            except Exception as e:
                print("failed to get version:", e)
