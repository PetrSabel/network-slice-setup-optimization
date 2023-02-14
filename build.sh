sudo docker build -t dev_test -f Dockerfile.dev_test ./
sudo docker build -t service_migration --file ./Dockerfile.server ./
sudo mn -c
sudo docker container rm -f $(docker container ls -aq)
ryu-manager --observe-links controller.py
