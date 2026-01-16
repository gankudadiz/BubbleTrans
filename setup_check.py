import sys
import subprocess
import importlib.util

REQUIRED_PACKAGES = {
    "PyQt6": "PyQt6",
    "paddleocr": "paddleocr",
    "paddle": "paddlepaddle",
    "openai": "openai",
    "PIL": "Pillow",
    "requests": "requests"
}

def check_package(package_name, install_name):
    print(f"Checking {package_name}...", end=" ")
    if importlib.util.find_spec(package_name):
        print("OK")
        return True
    else:
        print("MISSING")
        return False

def install_package(install_name):
    print(f"Installing {install_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", install_name])
        print(f"Successfully installed {install_name}")
        return True
    except subprocess.CalledProcessError:
        print(f"Failed to install {install_name}")
        return False

def main():
    print("=== BubbleTrans Environment Check ===")
    all_good = True
    missing_packages = []

    for package_name, install_name in REQUIRED_PACKAGES.items():
        if not check_package(package_name, install_name):
            all_good = False
            missing_packages.append(install_name)

    if not all_good:
        print("\nMissing dependencies detected.")
        choice = input(f"Do you want to try installing missing packages? ({', '.join(missing_packages)}) [Y/n]: ").strip().lower()
        if choice in ['', 'y', 'yes']:
            for pkg in missing_packages:
                if not install_package(pkg):
                    print("Error: Installation failed. Please check your internet connection or try manually.")
                    sys.exit(1)
            print("\nAll dependencies installed successfully!")
        else:
            print("Please install missing packages manually to run BubbleTrans.")
            sys.exit(1)
    else:
        print("\nEnvironment is ready!")

if __name__ == "__main__":
    main()
