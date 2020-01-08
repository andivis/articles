# articles

## Installation

1. Make sure Python 3.6 or higher is installed
1. Open a terminal window
2. Clone this repository
3. Run the commands below. Depending on your system you may need run `pip3` instead of `pip`.

```
pip install arvix
pip install lxml
pip install wget
```

## Instructions

1. Open a terminal window
2. Optionally, edit the `options.ini` file to your liking
3. Run `python articles.py -w input_websites.txt -s input_search_terms.txt`
4. Depending on your system you may need run `python3` instead of `python`.

## Options

- `maximumResultsPerKeyword`: How many pdf's to download for a given site/keyword combination. -1 means no limit. Default 25000.
- `onlyOneCopyPerPdf`: Only download a pdf if it does not exist anywhere in the output directory, including previous runs of this app. 1 means yes. 0 means no. Default 1.
- `minimumHoursBetweenRuns`: How many hours to wait before repeating a given site/keyword combination. Default is 12.