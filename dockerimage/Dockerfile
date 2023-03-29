FROM ubuntu

RUN apt-get update && \
  apt-get install -y openssh-server sudo && \
  mkdir /run/sshd && \
  adduser ubuntu --disabled-password --uid 2000 --gecos "" && \
  echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers 

RUN mkdir /home/ubuntu/.ssh && chmod go-rx /home/ubuntu/.ssh && chown ubuntu:ubuntu /home/ubuntu/.ssh

COPY setup-ssh.sh /home/ubuntu/setup-ssh.sh
#WORKDIR /home/ubunu
#USER ubuntu
