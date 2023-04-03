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

# install docker (just the command line tool, not the service) 

RUN sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
RUN echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
RUN apt-get update
RUN sudo apt-get install -y docker-ce-cli

RUN mkdir /home/ubuntu/.ssh && chmod go-rx /home/ubuntu/.ssh && chown ubuntu:ubuntu /home/ubuntu/.ssh

