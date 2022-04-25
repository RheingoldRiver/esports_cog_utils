import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="esports_cog_utils",
    version="0.0.1",
    author="RheingoldRiver",
    author_email="river.esports@gmail.com",
    description="River's Red cog tools",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/RheingoldRiver/esports_cog_utils",
    packages=setuptools.find_packages(),
    python_requires='>=3.6',
    # install_requires=['mwclient', 'mwparserfromhell'],
    dependency_links=['mwrogue']
)
