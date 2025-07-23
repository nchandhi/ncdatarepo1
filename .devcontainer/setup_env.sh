#!/bin/bash

git fetch
git pull

# provide execute permission to quotacheck script
sudo chmod +x ./infra/scripts/checkquota_km.sh
sudo chmod +x ./infra/scripts/quota_check_params.sh
sudo chmod +x ./infra/scripts/run_process_data_scripts.sh
sudo chmod +x ./infra/scripts/docker-build.sh
sudo chmod +x ./infra/scripts/docker-build.ps1