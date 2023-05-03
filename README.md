`hermitcrab`: A simple way to provision a development enviornment on google
cloud platform.

# Motivation

Being able to spin up a machine on the cloud is useful when working with
large data that live on the cloud. However, the realities of maintaining a
machine on the cloud are a fair amount of work, especially if one doesn't
have a lot of experience with GCP and linux.

Problem 1: The `gcloud` CLI to GCP is extremely flexible, but that flexibility makes it
harder to use. Commands tend to all have a lot of options and there's a fair
amount of typing to get to the command you want.

`hermit` tries to be a slimmed down CLI providing the core functionality a
developer who wants a dev environment on the cloud would need.
It does this by having sensible defaults for creating and lots of paranoid
santity checks to ensure operations do what's expected. In the result of a
problem, logs are kept for postmortems.

Problem 2: When people manage their own servers, there's a tendency for
packages to get installed locally in an adhoc fashion. This results in
difficulty reconstructing the state of the server if someone else would like
the same environment. It also runs the risk of the environment breaking and
not having a good way to backtrack to a sane state.

The solution taken by hermit-crab is to encourage the use of Docker to manage system
installed tools and libraries. By having the system files coming from a
docker image, we have the recipe for how that environment captured in the
Dockerfile which created that image. Those images can be shared as well as
versioned alongside the Dockerfiles used to create them.

# Commands

```
hermit create [name] [disk_in_gb] [docker_image] \
   --project [project] --zone [zone]
```

Creates a persistent disk to hold data, and creates a configuration file in
`~/.hermit/instances` with the information need to create a VM with this
disk mounted.

This will also update your `~/.ssh/config` file with information that ssh
can use to seamlessly connect to your instance when its running.

Example: `hermit create test-hermit 50 us.gcr.io/broad-achilles/hermitcrab --project broad-achilles --zone us-central1-a`

```
hermit up [name]
```

Starts an instance for the config with the given name. The created instance
will have the same name as the configuration. If no name is provided, it
defaults to "default".

![Hermit crab provisioned server](docs/hermitcrabarch.png)


```
hermit down [name]
```

Deletes the instance, but the persistent disk and the image will remain. As
a result you can execute `hermit up` at a later time to reconstruct the
environment.

This is primarily to shut down the instance to save on costs. However,
shutting it down are bringing it back up is also a good way to reset the
system files to their original state from the docker image.

# Cautionary notes

## Docker

Since "ssh name" takes to you to a shell within a container, and the docker
demon runs _outside_ of the container, you may encounter surprising
behavior. For example mounting directories other than /home/ubuntu will not
work as expected because it will use the filepath outside of the container.

Mounting locations under /home/ubuntu, however, will work because the 
same directory named /home/ubuntu exists inside and outside of the
container.

## Suspend on Idle

Every minute, there's a process that checks if the docker container has
used any network traffic. If yes, the machine runs normally. However, if
nothing has happened for the timeout `suspend_on_idle_timeout` to expire,
the server will suspend itself.

Even if you are running a large CPU heavy job and don't have
anything printed out as output, the idle check may decide the server is idle
and suspend it.

(I'm considering adding a check on "load average" as well, but at this time
it's only checking network activity.)

To unsuspend, simply re-run `hermit up`

# Troubleshooting

All gcloud commands are logged to hermit.log. That can be a good place to
look and understand what is going on.

If you want to connect to the VM outside of the container, you can via

```
gcloud compute ssh MACHINE_NAME
```

(where `MACHINE_NAME` is the name of the instance) 

Contrast this to running:

```
ssh MACHINE_NAME
```

which will log you into a session _inside_ the container running on
`MACHINE_NAME`.

If you encounter problems, you may want to look at the logs of the service which starts the inner container:

```
gcloud compute ssh MACHINE_NAME -- sudo journalctl -u container-sshd
```

Similar, if there's problems with the auto-suspend, you can look at the `suspend-on-idle` service:

```
gcloud compute ssh MACHINE_NAME -- sudo journalctl -u suspend-on-idle
```

Alternatively, you can always look at all the recent logs across the entire machine:

```
gcloud compute ssh MACHINE_NAME -- sudo journalctl --since "10 minutes ago"
```
