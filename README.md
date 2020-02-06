# Bamboo Scanner
## What is it
This is a simple script which written in a very short time for checking current plans in Bamboo if they have some specific variables in it with defined value.
It is using Python Bamboo API Client (https://github.com/liocuevas/python-bamboo-api)
I have included api directly inside the Git repo because of easy usage and also because of changing it a little bit.
Also this script is an example for Python Bamboo API Client.
## Where to use
It is useful for looping over your plans and search for some variable and looking for its value.
You can change the part that looking for specific variable and also you can change the branch part.
Because I am looking for the develop branch specific.
## How to use
python3 bambooscanner.py > scan.txt
## Dependencies
I have already included dependent Python Bamboo API Client but it also has some dependecies.
* BeautifulSoup