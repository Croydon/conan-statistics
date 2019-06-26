# Conan Statistics

Python tool to check statistics about Conan + Bintray

#### Running

    pip install -r requirements.txt
    export BINTRAY_USERNAME=<your-bintray-email>
    export BINTRAY_PASSWORD=<your-bintray-password>
    python conan-statistics.py

#### Requirements
* Firefox
* Gecko Driver
* Python

#### Troubleshooting

* Bintray Timeout: Increase request timeout: `export CONAN_REQUEST_TIMEOUT=3600`


#### LICENSE
[MIT](LICENSE)
