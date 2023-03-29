#docker run -w /work -v $HOME/.ssh/id_rsa:/root/authorized_keys -v $PWD/work:/work crab /usr/sbin/sshd -D
#COMMAND=bash
COMMAND="/usr/sbin/sshd -D -e"
docker run -it -v $PWD/work:/home/ubuntu -v $HOME/.ssh/id_rsa.pub:/home/ubuntu/.ssh-staging/authorized_keys -p3022:22  crab $COMMAND

