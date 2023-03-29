
gcloud compute disks create test-create-vol --size=50 --zone=us-central1-a --type=pd-standard

gcloud compute instances create create-vol \
  --image-family=cos-stable --image-project=cos-cloud \
  --zone=us-central1-a \
  --machine-type=n2-standard-2 \
  --metadata-from-file=user-data=cloudinit \
  --disk=name=test-create-vol,device-name=test-create-vol,auto-delete=no

#  --instance-termination-action=DELETE \
#  --provisioning-model=STANDARD \

# wait for compute instance to stop
gcloud compute instances list --filter=name=create-vol

gcloud compute instances delete create-vol


