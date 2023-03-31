`hermitcrab`: A simple way to provision a development enviornment on google
cloud platform.

# Problems

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

The solution here is to encourage the use of Docker to manage system
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
