import importlib
import json
import logging
import pathlib
import sys

class Issue(dict):

  logger = logging.getLogger(__name__)

  def __init__(self, id, **values):
    '''
    initialize an issue:
    issue = Issue(123, a='42', b='bits')
    or:
    values = {"a": "42", "b": "bits"}
    issue = Issue(123, **values)
    '''

    self.id = id
    self.values = values

    self.description = None
    self.recommendations = []
    self.references = []

    dict.__init__(self, **values)

  def format(self, templates):
    issue_template = templates[self.id]

    self._format_description(issue_template['description'])

    if 'recommendations' in issue_template:
      self._format_recommendations(issue_template['recommendations'])

    if 'references' in issue_template:
      self._format_references(issue_template['references'])

  def _format_description(self, description):
    self.description = description.format(**self.values)
    self['description'] = self.description

  def _format_recommendations(self, recommendations):
    self.recommendations = []
    for recommendation in recommendations:
      formatted_recommendation = recommendation.format(**self.values)
      self.recommendations.append(formatted_recommendation)
    self['recommendations'] = self.recommendations

  def _format_references(self, references):
    self.references = []
    for reference in references:
      formatted_reference = reference.format(**self.values)
      self.references.append(formatted_reference)

    self['references'] = self.references

class AbstractParser:

  logger = logging.getLogger(__name__)

  def __init__(self):
    '''
    initialize the parser.
    this method has to be extended by each concrete Parser class.
    in particular, the `name` and `file_type` variables have to be set:

    self.name = 'name'
    self.file_type = 'xml'
    '''

    self.services = {}

  def parse_files(self, files):
    if self.file_type not in files:
      return self.services

    for path in files[self.file_type]:
      try:
        self.parse_file(path)
      except Exception as e:
        self.__class__.logger.warning(f"could not parse file: {e}")

    return self.services

  def parse_file(self, path):
    '''
    parse a specific file.
    this method has to be implemented by each concrete Parser class.
    '''

    self.__class__.logger.info(f"parsing '{path}'")

    # extract the application/transport protocol from the filename
    filename = path.split('/')[-1]
    tokens = filename.split(',')
    self.application_protocol = tokens[0]
    self.transport_protocol = tokens[1]

    self.__class__.logger.debug(f"application/transport protocol: '{self.application_protocol}/{self.transport_protocol}'")

class AbstractAnalyzer:

  logger = logging.getLogger(__name__)

  def __init__(self, name, recommendations):
    '''
    initialize the analyzer.
    this method may need to be extended by each concrete Analyzer class.
    '''

    self.__class__.logger.debug(f"initializing analyzer '{name}'")

    self.name = name
    self.recommendations = recommendations
    self.services = []

  def set_parser(self, parser_name):
    '''
    set the parser that will be used to parse the results.
    '''

    self.__class__.logger.debug(f"setting parser to '{parser_name}'")

    module_path = pathlib.Path(
      pathlib.Path(__file__).resolve().parent,
      self.name,
      f'{parser_name}.py'
    )

    self.__class__.logger.debug(f"parser module '{module_path}'")

    if not module_path.exists():
      self.__class__.logger.error("parser does not exist!")
      sys.exit(f"unknown parser '{parser_name}'")

    self.parser_name = parser_name

    module_name = f'{__name__}.{self.name}.{parser_name}'
    self.__class__.logger.debug(f"importing parser '{module_name}'")
    module = importlib.import_module(module_name)
    self.parser = module.Parser()

  def analyze(self, files):
    '''
    analyze services based on some recommendations.
    this method has to be extended by each concrete Analyzer class
    '''

    if self.parser_name not in files:
      self.__class__.logger.error("nothing to analyze")
      sys.exit("\nnothing to analyze")
