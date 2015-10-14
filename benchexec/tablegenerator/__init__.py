"""
BenchExec is a framework for reliable benchmarking.
This file is part of BenchExec.

Copyright (C) 2007-2015  Dirk Beyer
All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

# prepare for Python 3
from __future__ import absolute_import, division, print_function, unicode_literals

import xml.etree.ElementTree as ET
import collections
import os.path
import glob
import json
import logging
import argparse
import re
import subprocess
import sys
import time
import tempita

from decimal import *

from .. import __version__
import benchexec.result as result

NAME_START = "results" # first part of filename of table

DEFAULT_OUTPUT_PATH = "results/"

LIB_URL = "http://cdn.jsdelivr.net"
LIB_URL_OFFLINE = "lib/javascript"

TEMPLATE_FILE_NAME = os.path.join(os.path.dirname(__file__), 'template.{format}')
TEMPLATE_FORMATS = ['html', 'csv']
TEMPLATE_ENCODING = 'UTF-8'

DEFAULT_TIME_PRECISION = 3

class Util:
    """
    This Class contains some useful functions for Strings, Files and Lists.
    """

    @staticmethod
    def get_file_list(shortFile):
        """
        The function get_file_list expands a short filename to a sorted list
        of filenames. The short filename can contain variables and wildcards.
        """

        # expand tilde and variables
        expandedFile = os.path.expandvars(os.path.expanduser(shortFile))

        # expand wildcards
        fileList = glob.glob(expandedFile)

        # sort alphabetical,
        # if list is emtpy, sorting returns None, so better do not sort
        if len(fileList) != 0:
            fileList.sort()
        else:
            logging.warning("No file matches '%s'.", shortFile)

        return fileList


    @staticmethod
    def extend_file_list(filelist):
        '''
        This function takes a list of files, expands wildcards
        and returns a new list of files.
        '''
        return [file for wildcardFile in filelist for file in Util.get_file_list(wildcardFile)]


    @staticmethod
    def split_number_and_unit(s):
        """
        Split a string into two parts: a number prefix and an arbitrary suffix.
        Splitting is done from the end, so the split is where the last digit
        in the string is (that means the prefix may include non-digit characters,
        if they are followed by at least one digit).
        """
        if not s:
            return (s, '')
        pos = len(s)
        while pos and not s[pos-1].isdigit():
            pos -= 1
        return (s[:pos], s[pos:])

    @staticmethod
    def remove_unit(s):
        """
        Remove a unit from a number string, or return the full string if it is not a number.
        """
        (prefix, suffix) = Util.split_number_and_unit(s)
        return suffix if prefix == '' else prefix

    @staticmethod
    def format_number(s, number_of_digits):
        """
        If the value is a number (or number plus one char),
        this function returns a string-representation of the number
        with a number of digits after the decimal separator.
        If the number has more digits, it is rounded, else zeros are added.

        If the value is no number, it is returned unchanged.
        """
        # if the number ends with "s" or another unit, remove it
        value, suffix = Util.split_number_and_unit((str(s) or '').strip())
        try:
            floatValue = float(value)
            return "{value:.{width}f}{suffix}".format(width=number_of_digits, value=floatValue, suffix=suffix)
        except ValueError: # if value is no float, don't format it
            return s


    @staticmethod
    def format_value(value, column):
        """
        Format a value nicely for human-readable output (including rounding).
        """
        if not value:
            return '-'

        number_of_digits = column.number_of_digits
        if number_of_digits is None and column.title.lower().endswith('time'):
            number_of_digits = DEFAULT_TIME_PRECISION

        if number_of_digits is None:
            return value
        return Util.format_number(value, number_of_digits)


    @staticmethod
    def to_decimal(s):
        # remove whitespaces and trailing units (e.g., in '1.23s')
        s, _ = Util.split_number_and_unit((s or '').strip())
        return Decimal(s) if s else Decimal()


    @staticmethod
    def collapse_equal_values(values, counts):
        """
        Take a tuple (values, counts), remove consecutive values and increment their count instead.
        """
        assert len(values) == len(counts)
        previousValue = values[0]
        previousCount = 0

        for value, count in zip(values, counts):
            if value != previousValue:
                yield (previousValue, previousCount)
                previousCount = 0
                previousValue = value
            previousCount += count

        yield (previousValue, previousCount)

    @staticmethod
    def get_column_value(sourcefileTag, columnTitle, default=None):
        for column in sourcefileTag.findall('column'):
            if column.get('title') == columnTitle:
                    return column.get('value')
        return default

    @staticmethod
    def flatten(list_):
        return [value for sublist in list_ for value in sublist]

    @staticmethod
    def json(obj):
        return tempita.html(json.dumps(obj, sort_keys=True))

    @staticmethod
    def prettylist(list_):
        if not list_:
            return ''

        # Filter out duplicate values while keeping order
        values = set()
        uniqueList = []
        for entry in list_:
            if not entry in values:
                values.add(entry)
                uniqueList.append(entry)

        return uniqueList[0] if len(uniqueList) == 1 \
            else '[' + '; '.join(uniqueList) + ']'

def parse_table_definition_file(file, all_columns):
    '''
    This function parses the input to get run sets and columns.
    The param 'file' is an XML file defining the result files and columns.

    If column titles are given in the XML file,
    they will be searched in the result files.
    If no title is given, all columns of the result file are taken.

    @return: a list of RunSetResult objects
    '''
    logging.info("Reading table definition from '%s'...", file)
    if not os.path.isfile(file):
        logging.error("File '%s' does not exist.", file)
        exit(1)

    def extract_columns_from_table_definition_file(xmltag):
        """
        Extract all columns mentioned in the result tag of a table definition file.
        """
        return [Column(c.get("title"), c.text, c.get("numberOfDigits"))
                for c in xmltag.findall('column')]

    runSetResults = []
    try:
        tableGenFile = ET.ElementTree().parse(file)
    except ET.ParseError as e:
        logging.error('Table file {} is invalid: {}'.format(file, e))
        exit(1)
    if 'table' != tableGenFile.tag:
        logging.error("Table file {} is invalid: It's root element is not named 'table'.".format(file))
        exit(1)

    defaultColumnsToShow = extract_columns_from_table_definition_file(tableGenFile)

    base_dir = os.path.dirname(file)

    for resultTag in tableGenFile.findall('result'):
        if not 'filename' in resultTag.attrib:
            logging.warning("Result tag without filename attribute in file '%s'.", file)
            continue
        columnsToShow = extract_columns_from_table_definition_file(resultTag) or defaultColumnsToShow
        filelist = Util.get_file_list(os.path.join(base_dir, resultTag.get('filename'))) # expand wildcards
        run_set_id = resultTag.get('id')
        runSetResults += [RunSetResult.create_from_xml(resultsFile, parse_results_file(resultsFile, run_set_id), columnsToShow, all_columns) for resultsFile in filelist]

    for unionTag in tableGenFile.findall('union'):
        columnsToShow = extract_columns_from_table_definition_file(unionTag) or defaultColumnsToShow
        result = RunSetResult([], collections.defaultdict(list), columnsToShow)

        for resultTag in unionTag.findall('result'):
            if not 'filename' in resultTag.attrib:
                logging.warning("Result tag without filename attribute in file '%s'.", file)
                continue
            filelist = Util.get_file_list(os.path.join(base_dir, resultTag.get('filename'))) # expand wildcards
            run_set_id = resultTag.get('id')
            for resultsFile in filelist:
                result.append(resultsFile, parse_results_file(resultsFile, run_set_id), all_columns)

        if result._xml_results:
            name = unionTag.get('title', unionTag.get('name'))
            if name:
                result.attributes['name'] = [name]
            runSetResults.append(result)

    return runSetResults


def get_task_id(task):
    """
    Return a unique identifier for a given task.
    @param task: the XML element that represents a task
    @return a tuple with filename of task as first element
    """
    task_id = [task.get('name'),
               task.get('properties'),
               task.get('runset'),
               ]
    return tuple(task_id)


class Column:
    """
    The class Column contains title, pattern (to identify a line in log_file),
    and number_of_digits of a column.
    It does NOT contain the value of a column.
    """
    def __init__(self, title, pattern, numOfDigits):
        self.title = title
        self.pattern = pattern
        self.number_of_digits = numOfDigits


loaded_tools = {}
def load_tool(result):
    """
    Load the module with the tool-specific code.
    """
    def load_tool_module(tool_module):
        if not tool_module:
            logging.warning('Cannot extract values from log files for benchmark results %s (missing attribute "toolmodule" on tag "result").',
                    Util.prettylist(result.attributes['name']))
            return None
        try:
            logging.debug('Loading %s' % tool_module)
            return __import__(tool_module, fromlist=['Tool']).Tool()
        except ImportError as ie:
            logging.warning('Missing module "%s", cannot extract values from log files (ImportError: %s).', tool_module, ie)
        except AttributeError:
            logging.warning('The module "%s" does not define the necessary class Tool, cannot extract values from log files.', tool_module)
        return None

    tool_module = result.attributes['toolmodule'][0] if 'toolmodule' in result.attributes else None
    if tool_module in loaded_tools:
        return loaded_tools[tool_module]
    else:
        result = load_tool_module(tool_module)
        loaded_tools[tool_module] = result
        return result


class RunSetResult():
    """
    The Class RunSetResult contains all the results of one execution of a run set:
    the sourcefiles tags (with sourcefiles + values), the columns to show
    and the benchmark attributes.
    """
    def __init__(self, xml_results, attributes, columns, summary={}):
        self._xml_results = xml_results
        self.attributes = attributes
        self.columns = columns
        self.summary = summary

    def get_tasks(self):
        """
        Return the list of task ids for these results.
        May be called only after collect_data()
        """
        return list(map(lambda r : r.task_id, self.results))

    def append(self, resultFile, resultElem, all_columns=False):
        """
        Append the result for one run. Needs to be called before collect_data().
        """
        self._xml_results += _get_run_tags_from_xml(resultElem)
        for attrib, values in RunSetResult._extract_attributes_from_result(resultFile, resultElem).items():
            self.attributes[attrib].extend(values)

        if not self.columns:
            self.columns = RunSetResult._extract_existing_columns_from_result(resultFile, resultElem, all_columns)

    def collect_data(self, correct_only):
        """
        Load the actual result values from the XML file and the log files.
        This may take some time if many log files have to be opened and parsed.
        """
        self.results = []

        def get_value_from_logfile(lines, identifier):
            """
            This method searches for values in lines of the content.
            It uses a tool-specific method to so.
            """
            return load_tool(self).get_value_from_output(lines, identifier)

        for xml_result in self._xml_results:
            self.results.append(RunResult.create_from_xml(xml_result,
                                                          get_value_from_logfile,
                                                          self.columns,
                                                          correct_only))

        del self._xml_results

    @staticmethod
    def create_from_xml(resultFile, resultElem, columns=None, all_columns=False):
        '''
        This function extracts everything necessary for creating a RunSetResult object
        from the "result" XML tag of a benchmark result file.
        It returns a RunSetResult object, which is not yet fully initialized.
        To finish initializing the object, call collect_data()
        before using it for anything else
        (this is to separate the possibly costly collect_data() call from object instantiation).
        '''
        attributes = RunSetResult._extract_attributes_from_result(resultFile, resultElem)

        if not columns:
            columns = RunSetResult._extract_existing_columns_from_result(resultFile, resultElem, all_columns)

        summary = RunSetResult._extract_summary_from_result(resultElem, columns)

        return RunSetResult(_get_run_tags_from_xml(resultElem),
                attributes, columns, summary)

    @staticmethod
    def _extract_existing_columns_from_result(resultFile, resultElem, all_columns):
        run_results = _get_run_tags_from_xml(resultElem)
        if not run_results:
            logging.warning("Result file '%s' is empty.", resultFile)
            return []
        else: # show all available columns
            columnNames = set()
            columns = []
            for s in run_results:
                for c in s.findall('column'):
                    title = c.get('title')
                    if not title in columnNames \
                            and (all_columns or c.get('hidden') != 'true'):
                        columnNames.add(title)
                        columns.append(Column(title, None, None))
            return columns


    @staticmethod
    def _extract_attributes_from_result(resultFile, resultTag):
        attributes = collections.defaultdict(list)

        # Defaults
        attributes['name'  ] = [resultTag.get('benchmarkname')]
        attributes['branch'] = [os.path.basename(resultFile).split('#')[0] if '#' in resultFile else '']

        # Update with real values
        for attrib, value in resultTag.attrib.items():
            attributes[attrib] = [value]

        # Add system information if present
        for systemTag in sorted(resultTag.findall('systeminfo'),
                                key=lambda systemTag: systemTag.get('hostname', 'unknown')):
            cpuTag = systemTag.find('cpu')
            attributes['os'   ].append(systemTag.find('os').get('name'))
            attributes['cpu'  ].append(cpuTag.get('model'))
            attributes['cores'].append( cpuTag.get('cores'))
            attributes['freq' ].append(cpuTag.get('frequency'))
            attributes['turbo'].append(cpuTag.get('turboboostActive'))
            attributes['ram'  ].append(systemTag.find('ram').get('size'))
            attributes['host' ].append(systemTag.get('hostname', 'unknown'))

        return attributes

    @staticmethod
    def _extract_summary_from_result(resultTag, columns):
        summary = collections.defaultdict(list)

        # Add summary for columns if present
        for column in resultTag.findall('column'):
            title = column.get('title')
            if title in (c.title for c in columns):
                summary[title] = column.get('value')

        return summary


def _get_run_tags_from_xml(result_elem):
    return result_elem.findall('run') + result_elem.findall('sourcefile')


def parse_results_file(resultFile, run_set_id=None):
    '''
    This function parses a XML file with the results of the execution of a run set.
    It returns the "result" XML tag.
    @param resultFile: The file name of the XML file with the results.
    @param run_set_id: An optional identifier of this set of results.
    '''
    if not os.path.isfile(resultFile):
        logging.error("File '%s' not found.", resultFile)
        exit(1)

    logging.info('    %s', resultFile)

    try:
        resultElem = ET.ElementTree().parse(resultFile)
    except ET.ParseError as e:
        logging.error('Result file {} is invalid: {}'.format(resultFile, e))
        exit(1)

    if resultElem.tag not in ['result', 'test']:
        logging.error(
            "XML file with benchmark results seems to be invalid.\n"
            + "The root element of the file is not named 'result' or 'test'.\n" \
            + "If you want to run a table-definition file,\n"\
            + "you should use the option '-x' or '--xml'.")
        exit(1)

    if run_set_id is not None:
        for sourcefile in _get_run_tags_from_xml(resultElem):
            sourcefile.set('runset', run_set_id)

    insert_logfile_names(resultFile, resultElem)
    return resultElem

def insert_logfile_names(resultFile, resultElem):
    # get folder of logfiles (truncate end of XML file name and append .logfiles instead)
    log_folder = resultFile[0:resultFile.rfind('.results.')] + '.logfiles/'

    # append begin of filename
    runSetName = resultElem.get('name')
    if runSetName is not None:
        blockname = resultElem.get('block')
        if blockname is None:
            log_folder += runSetName + "."
        elif blockname == runSetName:
            pass # real runSetName is empty
        else:
            assert runSetName.endswith("." + blockname)
            runSetName = runSetName[:-(1 + len(blockname))] # remove last chars
            log_folder += runSetName + "."

    # for each file: append original filename and insert log_file_name into sourcefileElement
    for sourcefile in _get_run_tags_from_xml(resultElem):
        log_file_name = os.path.basename(sourcefile.get('name')) + ".log"
        sourcefile.set('logfile', log_folder + log_file_name)


def merge_tasks(runset_results):
    """
    This function merges the results of all RunSetResult objects.
    If necessary, it can merge lists of names: [A,C] + [A,B] --> [A,B,C]
    and add dummy elements to the results.
    It also ensures the same order of tasks.
    """
    task_list = []
    task_set = set()
    for runset in runset_results:
        index = -1
        currentresult_taskset = set()
        for task in runset.get_tasks():
            if task in currentresult_taskset:
                logging.warning("Task '%s' is present twice, skipping it.", task[0])
            else:
                currentresult_taskset.add(task)
                if task not in task_set:
                    task_list.insert(index+1, task)
                    task_set.add(task)
                    index += 1
                else:
                    index = task_list.index(task)

    merge_task_lists(runset_results, task_list)

def merge_task_lists(runset_results, tasks):
    """
    Set the filelists of all RunSetResult elements so that they contain the same files
    in the same order. For missing files a dummy element is inserted.
    """
    for runset in runset_results:
        # create mapping from id to RunResult object
        # Use reversed list such that the first instance of equal tasks end up in dic
        dic = dict([(run_result.task_id, run_result) for run_result in reversed(runset.results)])
        runset.results = [] # clear and repopulate results
        for task in tasks:
            run_result = dic.get(task)
            if run_result is None:
                logging.info("    no result for task '%s'", task[0])
                # create an empty dummy element
                run_result = RunResult(task, None, result.CATEGORY_MISSING, 0, None,
                                       runset.columns, [None]*len(runset.columns))
            runset.results.append(run_result)


def find_common_tasks(runset_results):
    tasks_in_first_runset = runset_results[0].get_tasks()

    task_set = set(tasks_in_first_runset)
    for result in runset_results:
        task_set = task_set & set(result.get_tasks())

    task_list = []
    if not task_set:
        logging.warning('No tasks are present in all benchmark results.')
    else:
        task_list = [task for task in tasks_in_first_runset if task in task_set]
        merge_task_lists(runset_results, task_list)


class RunResult:
    """
    The class RunResult contains the results of a single verification run.
    """
    def __init__(self, task_id, status, category, score, log_file, columns, values):
        assert(len(columns) == len(values))
        self.task_id = task_id
        self.status = status
        self.log_file = log_file
        self.columns = columns
        self.values = values
        self.category = category
        self.score = score

    @staticmethod
    def create_from_xml(sourcefileTag, get_value_from_logfile, listOfColumns, correct_only):
        '''
        This function collects the values from one run.
        Only columns that should be part of the table are collected.
        '''

        def read_logfile_lines(logfilename):
            if not logfilename: return []
            try:
                with open(logfilename, 'rt') as logfile:
                    return logfile.readlines()
            except IOError as e:
                logging.warning("Could not read value from logfile: %s", e)
                return []

        status = Util.get_column_value(sourcefileTag, 'status', '')
        category = Util.get_column_value(sourcefileTag, 'category', result.CATEGORY_MISSING)
        score = result.score_for_task(sourcefileTag.get('name'),
                                      sourcefileTag.get('properties', '').split(),
                                      category)
        logfileLines = None

        values = []

        for column in listOfColumns: # for all columns that should be shown
            value = None # default value
            if column.title.lower() == 'score':
                value = str(score)
            elif column.title.lower() == 'status':
                value = status

            elif not correct_only or category == result.CATEGORY_CORRECT:
                if not column.pattern: # collect values from XML
                    value = Util.get_column_value(sourcefileTag, column.title)

                else: # collect values from logfile
                    if logfileLines is None: # cache content
                        logfileLines = read_logfile_lines(sourcefileTag.get('logfile'))

                    value = get_value_from_logfile(logfileLines, column.pattern)

            if column.number_of_digits is not None:
                value = Util.format_number(value, column.number_of_digits)

            values.append(value)

        return RunResult(get_task_id(sourcefileTag), status, category, score, sourcefileTag.get('logfile'), listOfColumns, values)


class Row:
    """
    The class Row contains all the results for one sourcefile (a list of RunResult instances).
    It is identified by the name of the source file and optional additional data
    (such as the property).
    It corresponds to one complete row in the final tables.
    """
    def __init__(self, results):
        assert results
        self.results = results
        self.id = results[0].task_id
        assert len(set(r.task_id for r in results)) == 1, "not all results are for same task"
        self.filename = self.id[0]
        self.properties = self.id[1].split() if self.id[1] else []

    def set_relative_path(self, common_prefix, base_dir):
        """
        generate output representation of rows
        """
        # make path relative to directory of output file if necessary
        self.file_path = self.filename if os.path.isabs(self.filename) \
                                 else os.path.relpath(self.filename, base_dir)

        self.short_filename = self.filename.replace(common_prefix, '', 1)

def rows_to_columns(rows):
    """
    Convert a list of Rows into a column-wise list of list of RunResult
    """
    return zip(*[row.results for row in rows])


def get_rows(runSetResults):
    """
    Create list of rows with all data. Each row consists of several RunResults.
    """
    rows = []
    for task_results in zip(*[runset.results for runset in runSetResults]):
        rows.append(Row(task_results))

    return rows


def filter_rows_with_differences(rows):
    """
    Find all rows with differences in the status column.
    """
    if not rows:
        # empty table
        return []
    if len(rows[0].results) == 1:
        # table with single column
        return []

    def all_equal_result(listOfResults):
        allStatus = set([result.status for result in listOfResults if result.status])
        allStatus.discard(None)
        return len(allStatus) <= 1

    rowsDiff = [row for row in rows if not all_equal_result(row.results)]

    if len(rowsDiff) == 0:
        logging.info("---> NO DIFFERENCE FOUND IN COLUMN 'STATUS'")
    elif len(rowsDiff) == len(rows):
        logging.info("---> DIFFERENCES FOUND IN ALL ROWS, NO NEED TO CREATE DIFFERENCE TABLE")
        return []

    return rowsDiff



def get_table_head(runSetResults, commonFileNamePrefix):

    # This list contains the number of columns each run set has
    # (the width of a run set in the final table)
    # It is used for calculating the column spans of the header cells.
    runSetWidths = [len(runSetResult.columns) for runSetResult in runSetResults]

    for runSetResult in runSetResults:
        # Ugly because this overwrites the entries in the map,
        # but we don't need them anymore and this is the easiest way
        for key in runSetResult.attributes:
            if key == 'turbo':
                turbo_values = list(set(runSetResult.attributes['turbo']))
                if len(turbo_values) > 1:
                    turbo = 'mixed'
                elif turbo_values[0] == 'true':
                    turbo = 'enabled'
                elif turbo_values[0] == 'false':
                    turbo = 'disabled'
                else:
                    turbo = None
                runSetResult.attributes['turbo'] = ', Turbo Boost {}'.format(turbo) if turbo else ''
            else:
                runSetResult.attributes[key] = Util.prettylist(runSetResult.attributes[key])

    def get_row(rowName, format_string, collapse=False, onlyIf=None, default='Unknown'):
        def format_cell(attributes):
            if onlyIf and not onlyIf in attributes:
                formatStr = default
            else:
                formatStr = format_string
            return formatStr.format(**attributes)

        values = [format_cell(runSetResult.attributes) for runSetResult in runSetResults]
        if not any(values): return None # skip row without values completely

        valuesAndWidths = list(Util.collapse_equal_values(values, runSetWidths)) \
                          if collapse else list(zip(values, runSetWidths))

        return tempita.bunch(id=rowName.lower().split(' ')[0],
                             name=rowName,
                             content=valuesAndWidths)

    firstBenchmarkName = runSetResults[0].attributes['benchmarkname']
    allBenchmarkNamesEqual = \
        all(r.attributes['benchmarkname'] == firstBenchmarkName   for r in runSetResults) or \
        all(r.attributes['benchmarkname'] == r.attributes['name'] for r in runSetResults)

    titles      = [column.title for runSetResult in runSetResults for column in runSetResult.columns]
    runSetWidths1 = [1]*sum(runSetWidths)
    titleRow    = tempita.bunch(id='columnTitles', name=commonFileNamePrefix,
                                content=list(zip(titles, runSetWidths1)))

    return {'tool':    get_row('Tool', '{tool} {version}', collapse=True),
            'limit':   get_row('Limits', 'timelimit: {timelimit}, memlimit: {memlimit}, CPU core limit: {cpuCores}', collapse=True),
            'host':    get_row('Host', '{host}', collapse=True, onlyIf='host'),
            'os':      get_row('OS', '{os}', collapse=True, onlyIf='os'),
            'system':  get_row('System', 'CPU: {cpu} with {cores} cores, frequency: {freq}{turbo}; RAM: {ram}', collapse=True, onlyIf='cpu'),
            'date':    get_row('Date of execution', '{date}', collapse=True),
            'runset':  get_row('Run set', '{name}' if allBenchmarkNamesEqual else '{benchmarkname}.{name}'),
            'branch':  get_row('Branch', '{branch}'),
            'options': get_row('Options', '{options}'),
            'property':get_row('Propertyfile', '{propertyfiles}', collapse=True, onlyIf='propertyfiles', default=''),
            'title':   titleRow}


def select_relevant_id_columns(rows):
    """
    Find out which of the entries in Row.id are equal for all given rows.
    @return: A list of True/False values according to whether the i-th part of the id is always equal.
    """
    relevant_id_columns = [True] # first column (file name) is always relevant
    if rows:
        prototype_id = rows[0].id
        for column in range(1, len(prototype_id)):
            def id_equal_to_prototype(row):
                return row.id[column] == prototype_id[column]

            relevant_id_columns.append(not all(map(id_equal_to_prototype, rows)))
    return relevant_id_columns


def get_stats(rows):
    stats = [get_stats_of_run_set(runResults) for runResults in rows_to_columns(rows)] # column-wise
    rowsForStats = list(map(Util.flatten, zip(*stats))) # row-wise

    # Calculate maximal score and number of true/false files for the given properties
    count_true = count_false = max_score = 0
    for row in rows:
        if not row.properties:
            # properties missing for at least one task, result would be wrong
            count_true = count_false = 0
            logging.info('Missing property for %s.', row.filename)
            break
        correct_result = result.satisfies_file_property(row.filename, row.properties)
        if correct_result is True:
            count_true += 1
        elif correct_result is False:
            count_false += 1
        max_score += result.score_for_task(row.filename, row.properties, result.CATEGORY_CORRECT)
    task_counts = 'in total {0} true tasks, {1} false tasks'.format(count_true, count_false)

    if max_score:
        score_row = tempita.bunch(default=None, id='score',
                                  title='score ({0} tasks, max score: {1})'.format(len(rows), max_score),
                                  description=task_counts,
                                  content=rowsForStats[7])

    def indent(n):
        return '&nbsp;'*(n*4)

    return [tempita.bunch(default=None, title='total tasks', description=task_counts, content=rowsForStats[0]),
            tempita.bunch(default=None, title=indent(1)+'correct results', description='(property holds + result is true) OR (property does not hold + result is false)', content=rowsForStats[1]),
            tempita.bunch(default=None, title=indent(2)+'correct true', description='property holds + result is true', content=rowsForStats[2]),
            tempita.bunch(default=None, title=indent(2)+'correct false', description='property does not hold + result is false', content=rowsForStats[3]),
            tempita.bunch(default=None, title=indent(1)+'incorrect results', description='(property holds + result is false) OR (property does not hold + result is true)', content=rowsForStats[4]),
            tempita.bunch(default=None, title=indent(2)+'incorrect true', description='property does not hold + result is true', content=rowsForStats[5]),
            tempita.bunch(default=None, title=indent(2)+'incorrect false', description='property holds + result is false', content=rowsForStats[6]),
            ] + ([score_row] if max_score else [])


def get_stats_of_run_set(runResults):
    """
    This function returns the numbers of the statistics.
    @param runResults: All the results of the execution of one run set (as list of RunResult objects)
    """

    # convert:
    # [['TRUE', 0,1], ['FALSE', 0,2]] -->  [['TRUE', 'FALSE'], [0,1, 0,2]]
    # in python2 this is a list, in python3 this is the iterator of the list
    # this works, because we iterate over the list some lines below
    listsOfValues = zip(*[runResult.values for runResult in runResults])

    columns = runResults[0].columns
    statusList = [(runResult.category, runResult.status) for runResult in runResults]

    # collect some statistics
    totalRow = []
    correctRow = []
    correctTrueRow = []
    correctFalseRow = []
    incorrectRow = []
    wrongTrueRow = []
    wrongFalseRow = []
    scoreRow = []

    for column, values in zip(columns, listsOfValues):
        if column.title == 'status':
            total   = StatValue(len([runResult.status for runResult in runResults if runResult.status]))

            counts = collections.Counter((category, result.get_result_classification(status))
                                         for category, status in statusList)
            countCorrectTrue  = counts[result.CATEGORY_CORRECT, result.RESULT_CLASS_TRUE]
            countCorrectFalse = counts[result.CATEGORY_CORRECT, result.RESULT_CLASS_FALSE]
            countWrongTrue    = counts[result.CATEGORY_WRONG, result.RESULT_CLASS_TRUE]
            countWrongFalse   = counts[result.CATEGORY_WRONG, result.RESULT_CLASS_FALSE]

            correct = StatValue(countCorrectTrue + countCorrectFalse)
            correctTrue = StatValue(countCorrectTrue)
            correctFalse = StatValue(countCorrectFalse)
            incorrect = StatValue(countWrongTrue + countWrongFalse)
            wrongTrue   = StatValue(countWrongTrue)
            wrongFalse = StatValue(countWrongFalse)

            score = StatValue(sum(run_result.score for run_result in runResults))

        else:
            total, correct, correctTrue, correctFalse, incorrect, wrongTrue, wrongFalse = get_stats_of_number_column(values, statusList, column.title)
            score = ''

        if (total.sum, correct.sum, correctTrue.sum, correctFalse.sum, incorrect.sum, wrongTrue.sum, wrongFalse.sum) == (0,0,0,0,0,0,0):
            (total, correct, correctTrue, correctFalse, incorrect, wrongTrue, wrongFalse) = (None, None, None, None, None, None, None)

        totalRow.append(total)
        correctRow.append(correct)
        correctTrueRow.append(correctTrue)
        correctFalseRow.append(correctFalse)
        incorrectRow.append(incorrect)
        wrongTrueRow.append(wrongTrue)
        wrongFalseRow.append(wrongFalse)
        scoreRow.append(score)

    def replace_irrelevant(row):
        if not row:
            return
        count = row[0]
        if not count or not count.sum:
            for i in range(1, len(row)):
                row[i] = None

    replace_irrelevant(totalRow)
    replace_irrelevant(correctRow)
    replace_irrelevant(correctTrueRow)
    replace_irrelevant(correctFalseRow)
    replace_irrelevant(incorrectRow)
    replace_irrelevant(wrongTrueRow)
    replace_irrelevant(wrongFalseRow)
    replace_irrelevant(scoreRow)

    return (totalRow, correctRow, correctTrueRow, correctFalseRow, incorrectRow, wrongTrueRow, wrongFalseRow, scoreRow)


class StatValue:
    def __init__(self, sum, min=None, max=None, avg=None, median=None):  # @ReservedAssignment
        self.sum = sum
        self.min = min
        self.max = max
        self.avg = avg
        self.median = median

    def __str__(self):
        return str(self.sum)

    @classmethod
    def from_list(cls, values):
        if not values:
            return StatValue(0)

        return StatValue(sum(values),
                         min    = min(values),
                         max    = max(values),
                         avg    = float("{:.3f}".format(sum(values) / len(values))),
                         median = sorted(values)[len(values)//2],
                         )


def get_stats_of_number_column(values, categoryList, columnTitle):
    assert len(values) == len(categoryList)
    try:
        valueList = [Util.to_decimal(v) for v in values]
    except InvalidOperation as e:
        if columnTitle != "host": # we ignore values of column host, used in cloud-mode
            logging.warning("%s. Statistics may be wrong.", e)
        return (StatValue(0), StatValue(0), StatValue(0), StatValue(0), StatValue(0), StatValue(0), StatValue(0))

    valuesPerCategory = collections.defaultdict(list)
    for value, catStat in zip(valueList, categoryList):
        category, status = catStat
        if status is None:
            continue
        valuesPerCategory[category, result.get_result_classification(status)].append(value)

    return (StatValue.from_list(valueList),
            StatValue.from_list(valuesPerCategory[result.CATEGORY_CORRECT, result.RESULT_CLASS_TRUE]
                              + valuesPerCategory[result.CATEGORY_CORRECT, result.RESULT_CLASS_FALSE]),
            StatValue.from_list(valuesPerCategory[result.CATEGORY_CORRECT, result.RESULT_CLASS_TRUE]),
            StatValue.from_list(valuesPerCategory[result.CATEGORY_CORRECT, result.RESULT_CLASS_FALSE]),
            StatValue.from_list(valuesPerCategory[result.CATEGORY_WRONG, result.RESULT_CLASS_TRUE]
                              + valuesPerCategory[result.CATEGORY_WRONG, result.RESULT_CLASS_FALSE]),
            StatValue.from_list(valuesPerCategory[result.CATEGORY_WRONG, result.RESULT_CLASS_TRUE]),
            StatValue.from_list(valuesPerCategory[result.CATEGORY_WRONG, result.RESULT_CLASS_FALSE]),
            )


def get_regression_count(rows, ignoreFlappingTimeouts): # for options.dump_counts

    columns = list(rows_to_columns(rows))
    if len(columns) < 2:
        return 0 # no regressions with only one run

    timeouts = set()
    for runResults in columns[:-1]:
        timeouts |= set(index for (index, runResult) in enumerate(runResults) if runResult.status == 'TIMEOUT')

    def is_flapping_timeout(index, oldResult, newResult):
        return index in timeouts \
            and oldResult.status != 'TIMEOUT' \
            and newResult.status == 'TIMEOUT'

    def ignore_regression(oldResult, newResult):
        return oldResult.status == 'TIMEOUT' and newResult.status == 'OUT OF MEMORY' \
            or oldResult.status == 'OUT OF MEMORY' and newResult.status == 'TIMEOUT'

    regressions = 0
    for index, (oldResult, newResult) in enumerate(zip(columns[-2], columns[-1])):
        # regression can be only if result is different and new result is not correct
        if oldResult.status != newResult.status and newResult.category != result.CATEGORY_CORRECT:

            if not (ignoreFlappingTimeouts and is_flapping_timeout(index, oldResult, newResult)) \
                    and not ignore_regression(oldResult, newResult):
                regressions += 1
    return regressions


def get_counts(rows): # for options.dump_counts
    countsList = []

    for runResults in rows_to_columns(rows):
        counts = collections.Counter(runResult.category for runResult in runResults)
        countsList.append((counts[result.CATEGORY_CORRECT],
                           counts[result.CATEGORY_WRONG],
                           counts[result.CATEGORY_UNKNOWN]
                           + counts[result.CATEGORY_ERROR]
                           + counts[None], # for rows without a result
                          ))

    return countsList


def get_summary(runSetResults):
    summaryStats = []
    available = False
    for runSetResult in runSetResults:
        for column in runSetResult.columns:
            if column.title in runSetResult.summary and runSetResult.summary[column.title] != '':
                available = True
                value = runSetResult.summary[column.title]
            else:
                value = ''
            summaryStats.append(StatValue(value))

    if available:
        return tempita.bunch(default=None, title='local summary',
            description='(This line contains some statistics from local execution. Only trust those values, if you use your own computer.)',
            content=summaryStats)
    else:
        return None


def create_tables(name, runSetResults, rows, rowsDiff, outputPath, outputFilePattern, options):
    '''
    create tables and write them to files
    '''

    # get common folder of sourcefiles
    common_prefix = os.path.commonprefix(list(map(lambda r : r.filename, rows))) # maybe with parts of filename
    common_prefix = common_prefix[: common_prefix.rfind('/') + 1] # only foldername
    list(map(lambda row: Row.set_relative_path(row, common_prefix, outputPath), rows))

    head = get_table_head(runSetResults, common_prefix)
    run_sets_data = [runSetResult.attributes for runSetResult in runSetResults]
    run_sets_columns = [[column for column in runSet.columns] for runSet in runSetResults]
    run_sets_column_titles = [[column.title for column in runSet.columns] for runSet in runSetResults]

    relevant_id_columns = select_relevant_id_columns(rows)
    count_id_columns = relevant_id_columns.count(True)

    templateNamespace={'flatten': Util.flatten,
                       'json': Util.json,
                       'relpath': os.path.relpath,
                       'format_value': Util.format_value,
                       'split_number_and_unit': Util.split_number_and_unit,
                       'remove_unit': Util.remove_unit,
                       }

    def write_table(table_type, title, rows):
        stats = get_stats(rows)

        summary = get_summary(runSetResults)
        if summary and table_type != 'diff' and not options.correct_only and not options.common:
            stats.insert(1, summary)

        for template_format in (options.format or TEMPLATE_FORMATS):
            if outputFilePattern == '-':
                logging.info('Writing %s to stdout...', template_format.upper().ljust(4))
            else:
                outfile = os.path.join(outputPath, outputFilePattern.format(name=name, type=table_type, ext=template_format))
                logging.info('Writing %s into %s ...', template_format.upper().ljust(4), outfile)

            # read template
            Template = tempita.HTMLTemplate if template_format == 'html' else tempita.Template
            template_file = TEMPLATE_FILE_NAME.format(format=template_format)
            try:
                template_content = __loader__.get_data(template_file).decode(TEMPLATE_ENCODING)
            except NameError:
                with open(template_file, mode='r') as f:
                    template_content = f.read()
            template = Template(template_content, namespace=templateNamespace)

            result = template.substitute(
                        title=title,
                        head=head,
                        body=rows,
                        foot=stats,
                        run_sets=run_sets_data,
                        columns=run_sets_columns,
                        columnTitles=run_sets_column_titles,
                        relevant_id_columns=relevant_id_columns,
                        count_id_columns=count_id_columns,
                        lib_url=options.lib_url,
                        base_dir=outputPath,
                        )

            # write file
            if outputFilePattern == '-':
                print(result, end='')
            else:
                with open(outfile, 'w') as file:
                    file.write(result)

            if options.show_table and template_format == 'html':
                try:
                    with open(os.devnull, 'w') as devnull:
                        subprocess.Popen(['xdg-open', outfile],
                                         stdout=devnull, stderr=devnull)
                except OSError:
                    pass

    # write normal tables
    write_table("table", name, rows)

    # write difference tables
    if rowsDiff:
        write_table("diff", name + " differences", rowsDiff)

def basename_without_ending(file):
    name = os.path.basename(file)
    if name.endswith(".xml"):
        name = name[:-4]
    return name

def main(args=None):

    if args is None:
        args = sys.argv

    parser = argparse.ArgumentParser(
        fromfile_prefix_chars='@',
        description=
        """Create tables with the results of one or more benchmark executions.
           Command-line parameters can additionally be read from a file if file name prefixed with '@' is given as argument.
           Part of BenchExec: https://github.com/dbeyer/benchexec/"""
    )

    parser.add_argument("tables",
        metavar="RESULT",
        type=str,
        nargs='*',
        help="XML file with the results from the benchmark script"
    )
    parser.add_argument("-x", "--xml",
        action="store",
        type=str,
        dest="xmltablefile",
        help="XML file with the table definition."
    )
    parser.add_argument("-o", "--outputpath",
        action="store",
        type=str,
        dest="outputPath",
        help="Output path for the tables. If '-', the tables are written to stdout."
    )
    parser.add_argument("-n", "--name",
        action="store",
        type=str,
        dest="output_name",
        help="Base name of the created output files."
    )
    parser.add_argument("--ignore-erroneous-benchmarks",
        action="store_true",
        dest="ignore_errors",
        help="Ignore results where the was an error during benchmarking."
    )
    parser.add_argument("-d", "--dump",
        action="store_true", dest="dump_counts",
        help="Print summary statistics for regressions and the good, bad, and unknown counts."
    )
    parser.add_argument("--ignore-flapping-timeout-regressions",
        action="store_true", dest="ignoreFlappingTimeouts",
        help="For the regression-count statistics, do not count regressions to timeouts if the file already had timeouts before."
    )
    parser.add_argument("-f", "--format",
        action="append",
        choices=TEMPLATE_FORMATS,
        help="Which format to generate (HTML or CSV). Can be specified multiple times. If not specified, all are generated."
    )
    parser.add_argument("-c", "--common",
        action="store_true", dest="common",
        help="Put only sourcefiles into the table for which all benchmarks contain results."
    )
    parser.add_argument("--no-diff",
        action="store_false", dest="write_diff_table",
        help="Do not output a table with result differences between benchmarks."
    )
    parser.add_argument("--correct-only",
        action="store_true", dest="correct_only",
        help="Clear all results (e.g., time) in cases where the result was not correct."
    )
    parser.add_argument("--all-columns",
        action="store_true", dest="all_columns",
        help="Show all columns in tables, including those that are normally hidden."
    )
    parser.add_argument("--offline",
        action="store_const", dest="lib_url",
        const=LIB_URL_OFFLINE,
        default=LIB_URL,
        help="Don't insert links to http://www.sosy-lab.org, instead expect JS libs in libs/javascript."
    )
    parser.add_argument("--show",
        action="store_true", dest="show_table",
        help="Open the produced HTML table(s) in the default browser."
    )
    parser.add_argument("-q", "--quiet",
        action="store_true",
        help="Do not show informational messages, only warnings."
    )
    parser.add_argument("--version",
        action="version", version="%(prog)s " + __version__
    )

    options = parser.parse_args(args[1:])

    logging.basicConfig(format="%(levelname)s: %(message)s",
                        level=logging.WARNING if options.quiet else logging.INFO)

    name = options.output_name
    outputPath = options.outputPath
    if outputPath == '-':
        # write to stdout
        outputFilePattern = '-'
        outputPath = '.'
    else:
        outputFilePattern = "{name}.{type}.{ext}"

    if options.xmltablefile:
        if options.tables:
            logging.error("Invalid additional arguments '%s'.", " ".join(options.tables))
            exit(1)
        runSetResults = parse_table_definition_file(options.xmltablefile, options.all_columns)
        if not name:
            name = basename_without_ending(options.xmltablefile)

        if not outputPath:
            outputPath = os.path.dirname(options.xmltablefile)

    else:
        if options.tables:
            inputFiles = options.tables
        else:
            searchDir = outputPath or DEFAULT_OUTPUT_PATH
            logging.info("Searching result files in '%s'...", searchDir)
            inputFiles = [os.path.join(searchDir, '*.results*.xml')]

        inputFiles = Util.extend_file_list(inputFiles) # expand wildcards
        runSetResults = [RunSetResult.create_from_xml(file, parse_results_file(file), all_columns=options.all_columns) for file in inputFiles]

        if len(inputFiles) == 1:
            if not name:
                name = basename_without_ending(inputFiles[0])
            if not outputFilePattern == '-':
                outputFilePattern = "{name}.{ext}"
        else:
            if not name:
                name = NAME_START + "." + time.strftime("%Y-%m-%d_%H%M", time.localtime())

        if inputFiles and not outputPath:
            path = os.path.dirname(inputFiles[0])
            if all(path == os.path.dirname(file) for file in inputFiles):
                outputPath = path
            else:
                outputPath = DEFAULT_OUTPUT_PATH

    if not outputPath:
        outputPath = '.'

    if options.ignore_errors:
        filteredRunSets = []
        for runSet in runSetResults:
            if 'error' in runSet.attributes:
                logging.warning('Ignoring benchmark %s because of error: %s',
                                ", ".join(set(runSet.attributes['name'])),
                                ", ".join(set(runSet.attributes['error'])))
            else:
                filteredRunSets.append(runSet)
        runSetResults = filteredRunSets

    if not runSetResults:
        logging.error('No benchmark results found.')
        exit(1)

    # collect data
    logging.info('Collecting data...')
    for result in runSetResults:
        result.collect_data(options.correct_only)

    logging.info('Merging results...')
    if options.common:
        find_common_tasks(runSetResults)
    else:
        # merge list of run sets, so that all run sets contain the same tasks
        merge_tasks(runSetResults)

    rows     = get_rows(runSetResults)
    if not rows:
        logging.warning('No results found, no tables produced.')
        exit()
    rowsDiff = filter_rows_with_differences(rows) if options.write_diff_table else []

    logging.info('Generating table...')
    if not os.path.isdir(outputPath) and not outputFilePattern == '-':
        os.makedirs(outputPath)
    create_tables(name, runSetResults, rows, rowsDiff, outputPath, outputFilePattern, options)

    logging.info('done')

    if options.dump_counts: # print some stats for Buildbot
        print ("REGRESSIONS {}".format(get_regression_count(rows, options.ignoreFlappingTimeouts)))
        countsList = get_counts(rows)
        print ("STATS")
        for counts in countsList:
            print (" ".join(str(e) for e in counts))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logging.info('Script was interrupted by user.')
        pass
