FROM ubuntu

# The requirements for a docker image to work with hermitcrab:
# 1. There must be a user named "ubuntu" with uid 2000
# 2. They must be able to sudo without entering a password
# 3. sshd must be installed 

RUN apt-get update && \
  apt-get install -y openssh-server sudo && \
  mkdir /run/sshd && \
  adduser ubuntu --disabled-password --uid 2000 --gecos "" && \
  echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers 

RUN mkdir /home/ubuntu/.ssh && chmod go-rx /home/ubuntu/.ssh && chown ubuntu:ubuntu /home/ubuntu/.ssh

