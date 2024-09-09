from hermitcrab import gcp


def test_parse_docker_image_name():
    parsed = gcp.parse_docker_image_name(
        "us-central1-docker.pkg.dev/cds-docker-containers/docker/hermit-dev-env:v1"
    )
    expected = gcp.ArtifactRegistryPath(
        host="us-central1-docker.pkg.dev",
        port=443,
        path="cds-docker-containers/docker/hermit-dev-env",
        tag="v1",
        location="us-central1",
        project="cds-docker-containers",
        repository="docker",
        image_name="hermit-dev-env",
    )
    assert parsed == expected

    parsed = gcp.parse_docker_image_name(
        "us.gcr.io/cds-docker-containers/hermit-dev-env"
    )
    assert parsed == gcp.ContainerRegistryPath(
        host="us.gcr.io",
        port=443,
        path="cds-docker-containers/hermit-dev-env",
        tag="latest",
        region="us",
        project="cds-docker-containers",
        repository="us.gcr.io",
        image_name="hermit-dev-env",
    )
