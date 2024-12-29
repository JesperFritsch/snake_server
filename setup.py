from setuptools import setup, find_packages

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="snake_server",
    version="0.1.0",
    packages=find_packages(exclude=["snake_server.static"]),
    python_requires=">=3.12",
    entry_points={
        "console_scripts": [
            "run-snake-server=snake_server.main:main",  # Optional CLI entry point
        ],
    },
    include_package_data=True,
    # package_data={
    #     "snake_server": ["static/*"],  # Include everything in the static folder
    # },
    install_requires=requirements
)