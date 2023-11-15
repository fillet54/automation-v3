import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="automation-v3", # Replace with your own username
    version="3.0.0",
    author="Phillip Gomez",
    author_email="phillip.gomez@ngc.com",
    description="An automation test framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/fillet54/automationv3",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    install_requires=[],
    python_requires='>=3.10',
    include_package_data=True,
    entry_points = {
        'console_scripts': ['automation-v3=automationv3.editor.__main__:main'],
    }
)
