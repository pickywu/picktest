from setuptools import setup


APP = ["rpg.py"]
OPTIONS = {
    "argv_emulation": False,
    "packages": [
        "arcade",
        "cairo",
        "PIL",
        "pyglet",
        "pymunk",
        "pytiled_parser",
    ],
    "plist": {
        "CFBundleName": "RPG",
        "CFBundleDisplayName": "RPG",
        "CFBundleIdentifier": "tw.fatcat.pick.rpg",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
    },
}


setup(
    app=APP,
    name="RPG",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
