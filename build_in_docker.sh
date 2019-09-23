container=$(docker run --rm -it -d ubuntu-dev bash)
name=$(python setup.py sdist | grep removing | cut -d' ' -f2 | sed "s/'//g")
docker cp dist/${name}.tar.gz ${container}:/
docker exec ${container} tar xf /${name}.tar.gz
docker cp debian ${container}:/${name}
docker cp .git ${container}:/${name}
#docker exec ${container} sh -c "python3 -m venv venv && venv/bin/pip install -r ${name}/requirements.txt"
docker exec ${container} sh -c "cd ${name} && gbp dch --ignore-branch -a -S && dpkg-buildpackage -us -uc -b && mkdir /dist && cp ../*.deb /dist"
docker cp ${container}:/dist .
#docker exec -it ${container} bash
docker container stop ${container}
