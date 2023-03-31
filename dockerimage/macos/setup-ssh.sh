# Because on the mac, file permissions are lost, we mount the contents that 
# we want in .ssh into .ssh-staging and then copy them over and set the proper
# permissions
if [ -e $HOME/.ssh-staging ]; then
rsync -r $HOME/.ssh-staging $HOME/.ssh
chmod -R go-rx /home/ubuntu/.ssh
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
fi
