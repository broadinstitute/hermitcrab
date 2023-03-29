gcloud compute instances create test-create-vm \
  --image-family=cos-stable --image-project=cos-cloud \
  --zone=us-central1-a \
  --machine-type=n2-standard-2 \
  --metadata-from-file=user-data=cloudinit \
  --disk=name=test-create-vol,device-name=test-create-vol,auto-delete=no
  