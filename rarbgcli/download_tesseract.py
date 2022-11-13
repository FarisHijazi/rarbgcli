import wget
import zipfile
import os
from sys import platform

# TODO: check existing work with requests_html


def main(chdir="."):
    os.chdir(chdir)

    # download for each platform if statement
    if platform == "win32":
        tesseract_zip = wget.download("https://github.com/FarisHijazi/rarbgcli/releases/download/v0.0.7/Tesseract-OCR.zip", "Tesseract-OCR.zip")
        # extract the zip file
        with zipfile.ZipFile(tesseract_zip, "r") as zip_ref:
            zip_ref.extractall()  # you can specify the destination folder path here
        # delete the zip file downloaded above
        os.remove(tesseract_zip)
    elif platform in ["linux", "linux2"]:
        os.system("sudo apt-get install tesseract-ocr")
    else:
        raise Exception("Unsupported platform")


if __name__ == "__main__":
    # argparser to take in the directory to extract the driver to
    import argparse

    parser = argparse.ArgumentParser(description="Download the tesseract driver for your platform")
    parser.add_argument("--chdir", default=".", help="directory to extract the driver to")
    args = parser.parse_args()
    main(args.chdir)
