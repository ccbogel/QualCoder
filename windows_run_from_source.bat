@echo off
echo Starting %TIME%

:: 1. Create venv if not exists
if not exist .env (
    python -m venv .env
    echo Virtual environment created.
) else (
    echo Using existing virtual environment.
)

:: 2. Activate environment
:: 'call' is necessary to keep the script running after activation
echo Activating virtual environment.
call .env\Scripts\activate.bat

:: 3. Install requirements
python -m pip install --upgrade pip

if exist "requirements.txt" (
    echo Installing dependencies. Please wait, may take 10 minutes on first install.
    pip install -r requirements.txt
)

:: 4. Move to src folder
cd src
echo Modules installed. %TIME%

:: 5. Run python module
echo Please wait. Starting QualCoder.
python -m qualcoder

:: 6. Keep window open
pause
cd ../
deactivate
echo Exiting virtual environment.
