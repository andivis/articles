# articles

## Installation

1. Make sure Python 3.6 or higher and pip are installed. For example, on Ubuntu run the commands below in a terminal.

```
sudo apt install -y python3
sudo apt install -y python3-pip
```

2. Open a terminal window
3. Run the commands below. Depending on your system you may need run `pip` instead of `pip3`.

```
git clone https://github.com/andivis/articles.git
cd articles
pip install arxiv
pip install lxml
pip install wget
```

## Instructions

1. Open a terminal window. Cd to the directory containing `articles.py`. It's where you cloned the repository before.
2. Optionally, edit the `options.ini` file to your liking
3. Edit `input_search_terms.txt` to contain your desired search terms. Each line is a search term.
3. Run `python articles.py -w input_websites.txt -s input_search_terms.txt`
4. Depending on your system you may need run `python3` instead of `python`.

## Options

- `maximumResultsPerKeyword`: How many pdf's to download for a given site/keyword combination. -1 means no limit. Default 25000.
- `onlyOneCopyPerPdf`: Only download a pdf if it does not exist anywhere in the output directory, including previous runs of this app. 1 means yes. 0 means no. Default 1.
- `minimumHoursBetweenRuns`: How many hours to wait before repeating a given site/keyword combination. Default is 12.