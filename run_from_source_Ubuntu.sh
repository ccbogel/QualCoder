#!/bin/bash
# Make this script executable
# Run it by typing inside the Qualcoder folder: ./Ubuntu_run_from_source.sh

echo "Starting"
# Create venv
if [ -d ".env" ]; then
    echo "Virtual environment exists."
else
    echo "Creating virtual environment."
    python3 -m venv ".env"
fi

# Activate environment
source .env/bin/activate

# Install required modules
echo "Installing requirements. This may take 10 minutes."
python3 -m pip install --upgrade pip
pip install -r requirements.txt

# Move to src folder to then run qualcoder module
echo "Starting QualCoder."
cd src
python3 -m qualcoder

# Exit environment
cd ../
deactivate
echo "Exiting virtual environment."
