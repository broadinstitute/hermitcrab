
from hermitcrab.main import main

def test_end_to_end(vcr, tmphomedir):
    main(["create", "--project", "broad-achilles", "--zone", 
          "us-central1-a", "hermit-demo", "50", 
          "us.gcr.io/broad-achilles/hermitcrab:with-docker", "--boot-disk-size", "55"])
    main(["status"])
    main(["up"])
    main(["status"])
    main(["down"])
    main(["delete", "-f"])
