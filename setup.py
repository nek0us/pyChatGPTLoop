from setuptools import setup, find_packages 

with open("README.md", "r") as readme_file:
    readme = readme_file.read()

requirements = ["undetected-chromedriver>=3.2.1","PyVirtualDisplay>=3.0","markdownify>=0.11.6"] # 这里填依赖包信息

setup(
    name="pyChatGPTLoop",
    version="0.1.3",
    author="nek0us",
    author_email="nekouss@gmail.com",
    description="Added backtracking chat on the basis of [terry3041/pyChatGPT]",
    long_description=readme,
    long_description_content_type="text/markdown",
    url="https://github.com/nek0us/pyChatGPTLoop",
    packages=find_packages(),
    # Single module也可以：
    # py_modules=['timedd']
    install_requires=requirements,
    classifiers=[
	"Programming Language :: Python :: 3.9",
	"License :: OSI Approved :: MIT License",
    ],
)