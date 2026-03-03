"""Setup script for the Bank FD Rates Tool."""

from setuptools import setup, find_packages
import os

# Read the README file for long description
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Bank FD Rates Tool - A web scraping tool for extracting Fixed Deposit rates from bank websites."

# Read requirements from requirements.txt
def read_requirements():
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    with open(requirements_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="fd-rates-tool",
    version="1.0.0",
    author="FD Rates Tool Team",
    description="A web scraping tool for extracting Fixed Deposit rates from bank websites",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=read_requirements(),
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
    ],
    entry_points={
        "console_scripts": [
            "fd-rates-tool=main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)