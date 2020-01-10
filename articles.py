import sys
import json
import logging
import time
import configparser
import urllib
import datetime
import os
import random
from collections import OrderedDict
import requests
import lxml.html as lh
from pathlib import Path
import arxiv
import traceback
import helpers
from database import Database
from helpers import Api
from helpers import Downloader

class Articles:
    def run(self):
        self.initialize()

        # go through each site
        for item in self.sites:
            self.doItem(item)
            self.onItemIndex += 1

        self.cleanUp()

    def doItem(self, item):
        for keyword in self.keywords:
            self.showStatus(item, keyword)
        
            # already done?
            if self.isDone(item, keyword):
                continue

            try:
                # do the search and download the results
                self.lookUpItem(item, keyword)
                self.markDone(item, keyword)
            except Exception as e:
                # if something goes wrong, we just go to next keyword
                logging.error(f'Skipping. Something went wrong.')
                logging.debug(traceback.format_exc())                
                logging.error(e)

    def lookUpItem(self, site, keyword):
        siteName = helpers.getDomainName(site.get('url', ''))

        self.totalResults = 0
        
        articles = []

        # use pubmed's api
        if siteName == 'nih.gov':
            articles = self.nihSearch(site, keyword)
        # use arxiv's api
        elif siteName == 'arxiv.org':
            articles = self.arxivSearch(site, keyword)
        # get the website and parse it
        else:
            siteData = {}
            
            keywordWithPlusSigns = keyword.replace(' ', '+')
            
            if siteName == 'biorxiv.org':
                siteData = {
                    'url': f'https://www.biorxiv.org/search/{keywordWithPlusSigns}%20numresults%3A75%20sort%3Arelevance-rank',
                    'resultsXpath': "//a[@class = 'highwire-cite-linked-title']",
                    'totalResultsXpath': "//*[@id = 'search-summary-wrapper']",
                    'titleXpath': "./span[@class = 'highwire-cite-title']",
                    'urlPrefix': 'https://www.biorxiv.org',
                    'afterFirstPageSuffix': '?page={}'
                }
            elif siteName == 'medrxiv.org':
                siteData = {
                    'url': f'https://www.medrxiv.org/search/{keywordWithPlusSigns}%20numresults%3A75%20sort%3Arelevance-rank',
                    'resultsXpath': "//a[@class = 'highwire-cite-linked-title']",
                    'totalResultsXpath': "//*[@id = 'search-summary-wrapper']",
                    'titleXpath': "./span[@class = 'highwire-cite-title']",
                    'urlPrefix': 'https://www.medrxiv.org',
                    'afterFirstPageSuffix': '?page={}'
                }

            articles = self.genericSearch(site, keyword, siteData)

        i = 0
        
        # download all the pdf url's we found
        for article in articles:
            logging.info(f'Site {self.onItemIndex + 1} of {len(self.sites)}: {siteName}. Keyword {self.onKeywordIndex + 1} of {len(self.keywords)}: {keyword}. Downloading item {i + 1} of {len(articles)}: {article[0]}.')
                        
            self.outputResult(site, keyword, i + 1, article)

            i += 1

    def showStatus(self, item, keyword):
        siteName = helpers.getDomainName(item.get('url', ''))

        logging.info(f'Site {self.onItemIndex + 1} of {len(self.sites)}: {siteName}. Keyword {self.onKeywordIndex + 1} of {len(self.keywords)}: {keyword}.')

    # have enough results?
    def shouldStopForThisKeyword(self, index, log=True):
        result = False
        
        if index >= self.options['maximumResultsPerKeyword']:
            maximum = self.options['maximumResultsPerKeyword']
            
            if log:
                logging.info(f'Stopping. Reached the maximum of {maximum} results for this keyword.')
            
            result = True

        return result

    def nihSearch(self, site, keyword):
        results = []

        api = Api('http://eutils.ncbi.nlm.nih.gov')

        for i in range(0, 1000):
            pageResults = self.getNihPage(site, keyword, api, i, results, len(results))

            if not pageResults:
                logging.debug('Reached end of search results')
                break

            results += pageResults

            # have enough results?
            if self.shouldStopForThisKeyword(len(results)):
                break

            i += 1
        
        return results

    def getGenericSearchPage(self, site, keyword, siteData, pageIndex, existingResults, resultCount):
        results = []
        ids = []

        logging.info(f'Getting page {pageIndex + 1}')

        suffix = ''

        if pageIndex > 0:
            suffix = siteData.get('afterFirstPageSuffix', '')
            suffix = suffix.format(pageIndex)

        page = self.downloader.get(siteData['url'] + suffix)

        elements = self.downloader.getXpath(page, siteData['resultsXpath'])
        
        total = self.downloader.getXpath(page, siteData['totalResultsXpath'], True)
        total = helpers.numbersOnly(total)

        if not self.totalResults and total:
            self.totalResults = int(total)

            self.showResultCount()

            # log the search now because the download might fail
            self.logToCsvFiles(site, keyword, -1, [], '', False, True, False)

        urls = []
        i = resultCount
        
        # get information about each item
        for element in elements:
            if self.shouldStopForThisKeyword(i, False):
                break

            i += 1
           
            url = element.attrib['href']
            url = siteData['urlPrefix'] + url

            # avoids duplicates
            if url in urls:
                continue

            urls.append(url)

            pdfUrl = url + '.full.pdf'
                
            articleId = self.getLastAfterSplit(url, '/')

            title = self.downloader.getXpathInElement(element, siteData['titleXpath'])

            shortTitle = title

            if len(shortTitle) > 50:
                shortTitle = shortTitle[0:50] + '...'

            logging.info(f'Results: {len(urls)}. Url: {url}. Title: {shortTitle}.')
            
            # this allows us to know when we reached the final page
            if self.isInArticleList(existingResults, articleId):
                continue

            result = [articleId, pdfUrl, title]
            
            results.append(result)

        return results

    def showResultCount(self):
        maximumResults = self.options['maximumResultsPerKeyword']

        logging.info(f'Total number of results available: {self.totalResults}. Number of desired results: {maximumResults}.' )


    def isInArticleList(self, articleList, articleId):
        result = False

        for article in articleList:
            if len(article) >= 2 and article[0] == articleId:
                result = True
                break

        return result

    def getNihPage(self, site, keyword, api, pageIndex, existingResults, resultCount):
        results = []

        logging.info(f'Getting page {pageIndex + 1}')

        resultsPerPage = 1000
        start = pageIndex * resultsPerPage

        response = api.get(f'/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retstart={start}&retmax={resultsPerPage}&term={keyword}')

        if not self.totalResults:
            self.totalResults = response['esearchresult']['count']
            
            self.showResultCount()
            
            # log the search now because the download might fail
            self.logToCsvFiles(site, keyword, -1, [], '', False, True, False)

        i = resultCount
        
        for item in response['esearchresult']['idlist']:
            if self.shouldStopForThisKeyword(i, False):
                break

            # avoid duplicates
            if self.isInArticleList(existingResults, item):
                continue

            i += 1

            summaryResponse = api.get(f'/entrez/eutils/esummary.fcgi?db=pubmed&id={item}&retmode=json')

            title = ''

            if 'result' in summaryResponse and item in summaryResponse['result']:
                articleSummary = summaryResponse['result'][item]
                
                title = articleSummary.get('title', '')
                
                shortTitle = title

                if len(shortTitle) > 50:
                    shortTitle = shortTitle[0:50] + '...'

                logging.info(f'Results: {i}. Id: {item}. Title: {shortTitle}.')

                # write these results to a separate csv
                self.logNihResultToCsvFile(site, keyword, articleSummary)

            pdfUrl = self.getPdfUrlFromSciHub(site, item)

            if not pdfUrl:
                continue
            
            result = [item, pdfUrl, title]
            
            results.append(result)

        return results

    def arxivSearch(self, site, keyword):
        results = []

        maximumResults = self.options['maximumResultsPerKeyword']

        if maximumResults == -1:
            maximumResults = None

        items = arxiv.query(query=keyword,
                    id_list=[],
                    max_results=maximumResults,
                    start = 0,
                    sort_by="relevance",
                    sort_order="descending",
                    prune=True,
                    iterative=False,
                    max_chunk_results=1000)

        ids = []

        for item in items:
            id = item.get('id', '')
            id = self.getLastAfterSplit(id, '/')

            # avoids duplicates
            if id in ids:
                continue

            ids.append(id)

            pdfUrl = item.get('pdf_url', '')

            if not pdfUrl:
                siteName = helpers.getDomainName(site.get('url', ''))
                message = f'No pdf file found on {siteName} for {id}'
                logging.error(message)
                pdfUrl = f'Error: {message}'

            title = item.get('title', '')

            shortTitle = title

            if len(shortTitle) > 50:
                shortTitle = shortTitle[0:50] + '...'

            logging.info(f'Results: {len(results)}. Id: {id}. Title: {shortTitle}.')

            result = [id, pdfUrl, title]
            
            results.append(result)

        self.totalResults = len(results)

        self.showResultCount()

        # log the search now because the download might fail
        self.logToCsvFiles(site, keyword, -1, [], '', False, True, False)

        return results

    def getLastAfterSplit(self, s, splitter):
        result = ''

        fields = s.split(splitter)

        if len(fields) > 0:
            result = fields[-1]

        return result

    def getArticleId(self, site, pdfUrl):
        return getLastAfterSplit(pdfUrl, '/')

    def genericSearch(self, site, keyword, siteData):
        results = []

        for i in range(0, 1000):
            pageResults = self.getGenericSearchPage(site, keyword, siteData, i, results, len(results))

            if not pageResults:
                logging.debug('Reached end of search results')
                break

            results += pageResults

            # have enough results?
            if self.shouldStopForThisKeyword(len(results)):
                break

            i += 1
        
        return results

    def outputResult(self, site, keyword, resultNumber, article):
        siteName = helpers.getDomainName(site.get('url', ''))

        articleId = article[0]
        pdfUrl = article[1]

        downloaded = 'Not downloaded'

        if pdfUrl.startswith('Error: '):
            outputFileName = 'Nan'

            # it's the error message
            downloaded = pdfUrl
        else:
            subdirectory = f'{siteName}'
            fileName = f'{articleId}.pdf'

            outputFileName = os.path.join(self.options['outputDirectory'], subdirectory, fileName)

            helpers.makeDirectory(os.path.dirname(outputFileName))

            # no need to download again. still need to write to csv file.
            if pdfUrl == 'binary':
                logging.debug(f'Already wrote the binary file to {outputFileName}')
                downloaded = 'Downloaded successfully'
            # only download if necessary
            elif os.path.exists(outputFileName):
                logging.info(f'Already done. Output file {outputFileName} already exists.')
                return
            elif not self.existsInDirectory(fileName):
                logging.debug(f'Downloading. Output file does not exist.')
                success = self.downloader.downloadBinaryFile(pdfUrl, outputFileName)
                print('')

                if self.handleCaptcha(siteName, outputFileName):
                    downloaded = 'Captcha'
                    outputFileName = 'NaN'
                elif success:
                    downloaded = 'Downloaded successfully'
                else:
                    downloaded = 'Download failed'
                    outputFileName = 'NaN'
        
        # log to the csv file anyway
        self.logToCsvFiles(site, keyword, resultNumber, article, outputFileName, downloaded, False, True)

        self.waitBetween()

    # log to search log and/or pdf log
    def logToCsvFiles(self, site, keyword, resultNumber, article, outputFileName, downloaded, searchLog, pdfLog):
        helpers.makeDirectory(self.options['outputDirectory'])
        
        searchLogFileName = os.path.join(self.options['outputDirectory'], 'output_searchlog.csv')
        pdfLogFileName = os.path.join(self.options['outputDirectory'], 'output_pdf_log.csv')
        
        if searchLog and not os.path.exists(searchLogFileName):
            helpers.toFile('Date-Time,Search terms,Websites,Number of papers,Requested maximumResultsPerKeyword', searchLogFileName)

        if pdfLog and not os.path.exists(pdfLogFileName):
            helpers.toFile('Datetime, Search terms, Website, Result number, Total results requested, ID number, Title, Downloaded?, FileNamePath', pdfLogFileName)

        now = datetime.datetime.now().strftime('%m%d%y-%H%M%S')

        siteName = site.get('name', '')

        articleId = ''
        title = ''

        if len(article) >= 3:
            articleId = article[0]
            title = article[2]

        searchLogLine = [now, keyword, siteName, self.totalResults, self.options['maximumResultsPerKeyword']]
        pdfLogLine = [now, keyword, siteName, resultNumber, self.options['maximumResultsPerKeyword'], articleId, title, downloaded, outputFileName]

        if searchLog:
            self.appendCsvFile(searchLogLine, searchLogFileName)

        if pdfLog:
            self.appendCsvFile(pdfLogLine, pdfLogFileName)

    # writes article details to a csv file
    def logNihResultToCsvFile(self, site, keyword, article):
        name = site.get('name', '').lower()
        
        csvFileName = os.path.join(self.options['outputDirectory'], f'{name}_results.csv')
        
        if not os.path.exists(csvFileName):
            helpers.toFile('DateTime,Keyword,Title,URL,Description,Details,ShortDetails,Resource,Type,Identifiers,Db,EntrezUID,Properties', csvFileName)

        siteName = site.get('name', '')

        articleId = article.get('uid', '')
        properties = 'create date: ' + helpers.findBetween(article.get('sortpubdate', ''), '', ' ') + ' | first author: ' + article.get('sortfirstauthor', '')
        description = ''

        authors = []
        for author in article.get('authors', ''):
            authors.append(author.get('name', ''))

        description = ', '.join(authors) + '.'

        publicationTypes = ', '.join(article.get('pubtype', []))

        details = article.get('fulljournalname', '') + '. ' + article.get('elocationid', '') + '. ' + publicationTypes + '.'
        
        line = [
            datetime.datetime.now().strftime('%m%d%y-%H%M%S'),
            keyword,
            article.get('title', ''),
            f'/pubmed/{articleId}',
            description,
            details,
            article.get('fulljournalname', '') + '. ' + helpers.findBetween(article.get('sortpubdate', ''), '', '/'),
            'PubMed',
            publicationTypes,
            f'PMID:{articleId}',
            'pubmed',
            articleId,
            properties
        ]
        
        self.appendCsvFile(line, csvFileName)

    def appendCsvFile(self, line, fileName):
        import csv
        with open(fileName, "a", newline='\n', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file, delimiter=',')
            writer.writerow(line)

    def handleCaptcha(self, siteName, outputFileName):
        result = False

        if siteName != 'nih.gov':
            return result

        try:
            statinfo = os.stat(outputFileName)
        
            if statinfo.st_size < 1000 * 1000:
                file = helpers.getBinaryFile(outputFileName)

                if not file.startswith(b'%PDF'):
                    logging.error(f'Can\'t download this file. There is a captcha.')

                    # delete the file
                    if os.path.exists(outputFileName):
                        os.remove(outputFileName)
                    result = True
        except Exception as e:
            logging.error(e)

        return result

    def existsInDirectory(self, fileName):
        result = False;

        if self.options['directoryToCheckForDuplicates'] != 1:
            return result
        
        for file in helpers.listFiles(self.options['outputDirectory'], False):
            if helpers.fileNameOnly(file, True) == fileName:
                outputDirectory = self.options['outputDirectory']
                logging.info(f'Skipping. Output file already exists in {outputDirectory}.')
                result = True
                break

        return result

    def getPdfUrlFromSciHub(self, site, articleId):
        result = ''

        api = Api('https://sci-hub.tw')

        body = {
            'sci-hub-plugin-check': '',
            'request': articleId
        }
        
        try:
            response = api.post('/', body, False)

            # sometimes it returns the pdf directly
            if isinstance(response, bytes) and response.startswith(b'%PDF'):
                siteName = helpers.getDomainName(site.get('url', ''))
                outputFileName = os.path.join(self.options['outputDirectory'], siteName, f'{articleId}.pdf')

                logging.debug(f'Response is a pdf file. Writing it to {outputFileName}.')
                
                helpers.makeDirectory(os.path.dirname(outputFileName))
                helpers.toBinaryFile(response, outputFileName)

                return 'binary'

            result = self.downloader.getXpath(response, "//*[@id = 'buttons']//a[contains(@onclick, '.pdf')]", True, 'onclick')

            result = result.replace("location.href='", '')

            if result and not result.startswith('http'):
                result = 'https:' + result

            if result.endswith("'"):
                result = result[0:-1]
        except Exception as e:
            logging.error(e)

        if not result:
            siteName = helpers.getDomainName(api.urlPrefix)
            message = f'No result found on {siteName} for {articleId}'
            logging.error(message)
            result = f'Error: {message}'

        return result

    def download(self, url, site, keyword):
        pass
    
    def isDone(self, site, keyword):
        result = False;

        siteName = helpers.getDomainName(site.get('url', ''))

        keyword = keyword.replace("'", "''")

        directory = self.options['outputDirectory']

        siteName = self.database.getFirst('history', 'siteName', f"siteName= '{siteName}' and keyword = '{keyword}' and directory = '{directory}'", '', '')

        if siteName:
            logging.info(f'Skipping. Already done this item.')
            result = True

        return result

    # so we know not to repeat this site/keyword too soon
    def markDone(self, site, keyword):
        siteName = helpers.getDomainName(site.get('url', ''))

        keyword = keyword.replace("'", "''")

        item = {
            'siteName': siteName,
            'keyword': keyword,
            'directory': self.options['outputDirectory'],
            'gmDate': str(datetime.datetime.utcnow())
        }

        logging.debug(f'Inserting into database')
        logging.debug(item)
            
        self.database.insert('history', item)

    def waitBetween(self):
        secondsBetweenItems = self.options['secondsBetweenItems']

        if not secondsBetweenItems:
            return

        logging.info(f'Waiting {secondsBetweenItems} seconds')

        time.sleep(secondsBetweenItems)

    def setOptionFromParameter(self, optionName, parameterName):
        if not parameterName in sys.argv:
            return

        self.options[optionName] = helpers.getArgument(parameterName, False)

    def removeOldEntries(self):
        maximumDaysToKeepItems = self.options['maximumDaysToKeepItems']
        
        minimumDate = helpers.getDateStringSecondsAgo(maximumDaysToKeepItems * 24 * 60 * 60, True)
        
        logging.debug(f'Deleting entries older than {maximumDaysToKeepItems} days')
        self.database.execute(f"delete from history where gmDate < '{minimumDate}'")

    def cleanUp(self):
        self.database.close()

        logging.info('Done')

    def initialize(self):
        helpers.setUpLogging()

        logging.info('Starting\n')

        self.onItemIndex = 0
        self.onKeywordIndex = 0

        # to store the time we finished given sites/keyword combinations
        self.database = Database('database.sqlite')
        self.database.execute('create table if not exists history ( siteName text, keyword text, directory text, gmDate text, primary key(siteName, keyword, directory) )')

        self.downloader = Downloader()
        self.dateStarted = datetime.datetime.now().strftime('%m%d%y')
        
        outputDirectory = os.path.join(str(Path.home()), 'Desktop', f'WebSearch_{self.dateStarted}')

        # set default options
        self.options = {
            'inputWebsitesFile': 'input_websites.txt',
            'inputKeywordsFile': 'input_search_terms.txt',
            'outputDirectory': outputDirectory,
            'secondsBetweenItems': 0,
            'maximumDaysToKeepItems': 90,
            'maximumResultsPerKeyword': 25000,
            'directoryToCheckForDuplicates': ''
        }

        # read the options file
        helpers.setOptions('options.ini', self.options)

        # read command line parameters
        self.setOptionFromParameter('inputWebsitesFile', '-w')
        self.setOptionFromParameter('inputKeywordsFile', '-s')
        self.setOptionFromParameter('outputDirectory', '-d')

        # read websites file
        file = helpers.getFile(self.options['inputWebsitesFile'])
        file = helpers.findBetween(file, "['", "']")
        sites = file.split("', '")
        self.sites = []

        for item in sites:
            name = helpers.findBetween(item, '', ':')
            url = helpers.findBetween(item, ':', '')

            site = {
                'name': name,
                'url': url
            }

            self.sites.append(site)

        # read keywords file
        keywordsFile = helpers.getFile(self.options['inputKeywordsFile'])
        list = keywordsFile.splitlines()
        self.keywords = []

        for line in list:
            self.keywords.append(helpers.findBetween(line, "'", "'"))

        self.removeOldEntries()

articles = Articles()
articles.run()