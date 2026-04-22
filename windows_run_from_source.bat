echo Starting %TIME%

:: 1. Create venv if not exists
if not exist .env (
    python -m venv .env
    echo Virtual environment created.
)

:: 2. Activate environment
:: 'call' is necessary to keep the script running after activation
call .env\Scripts\activate.bat

:: 3. Install requirements

python -m pip install --upgrade pip

if exist "requirements.txt" (
    echo Installing dependencies. Please wait, may take 10 or more minutes.
    pip install -r requirements.txt
)

:: 4. Move to src folder
cd src

echo Modules installed. %TIME%


:: 5. Run python module
python -m qualcoder

:: 6. Keep window open
pause

cd ../

deactivate
