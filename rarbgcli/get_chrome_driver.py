import requests
import wget
import zipfile
import os
from sys import platform
from pathlib import Path

global platform_
platform_ = platform


def main(chdir="."):
    os.chdir(chdir)

    target_fpath = "chromedriver.exe" if platform == "win32" else "chromedriver"
    target_fpath = str((Path(chdir) / target_fpath).resolve())
    if os.path.isfile(target_fpath):
        return target_fpath

    # get the latest chrome driver version number
    url = "https://chromedriver.storage.googleapis.com/LATEST_RELEASE"
    response = requests.get(url)
    version_number = response.text

    global platform_
    if platform_ == "darwin":
        import cpuinfo

        # Just get the manufacturer of the processors
        manufacturer = cpuinfo.get_cpu_info().get("brand_raw")
        # 'Apple M1 Pro'
        if "m1" in manufacturer.lower():
            platform_ += "m1"

    os_specific = {
        "linux": "chromedriver_linux64.zip",
        "linux2": "chromedriver_linux64.zip",
        "darwin": "chromedriver_mac64.zip",
        "darwinm1": "chromedriver_mac64_m1.zip",
        "win32": "chromedriver_win32.zip",
    }

    # build the donwload url
    download_url = "https://chromedriver.storage.googleapis.com/" + version_number + "/" + os_specific[platform_]

    # download the zip file using the url built above
    latest_driver_zip = wget.download(download_url, "chromedriver.zip")

    # extract the zip file
    with zipfile.ZipFile(latest_driver_zip, "r") as zip_ref:
        zip_ref.extractall()  # you can specify the destination folder path here
    # delete the zip file downloaded above
    os.remove(latest_driver_zip)
    return target_fpath


if __name__ == "__main__":
    # argparser to take in the directory to extract the driver to
    import argparse

    parser = argparse.ArgumentParser(description="Download the latest chrome driver")
    parser.add_argument("--chdir", default=".", help="directory to extract the driver to")
    args = parser.parse_args()
    main(args.chdir)
