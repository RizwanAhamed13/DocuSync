from setuptools import setup, find_packages

setup(
    name="quad-cli",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click==8.1.7",
        "rich==13.7.1",
        "requests==2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "quad=cli.quad:cli",
        ],
    },
)
