#!/bin/sh

VERSION=`python -c "import rsproductwatcher; print(rsproductwatcher.__version__)"`
echo $VERSION
git add rsproductwatcher/version.py
git commit -m 'version bump'
git push \
&& git tag $VERSION \
&& git push --tags
