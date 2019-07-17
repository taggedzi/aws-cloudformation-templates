#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os.path
import time
import yaml
from bs4 import BeautifulSoup

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

import requests
from requests.exceptions import HTTPError

import logging
logging.basicConfig(level=logging.WARNING)

BASE_URL = 'https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide'
MAX_PAGES_TO_PULL = 0
MIN_TIME_BETWEEN_REQUESTS = 1
STARTING_PAGE = "aws-template-resource-type-ref.html"
TEMP_DIR = './scratch'
TEMPLATE_DIR = './templates'


top_level_resources = {}
resource_subtypes = {}


def get_resource_pages():
    root_url = f'{BASE_URL}/{STARTING_PAGE}'
    logging.info(json.dumps({
        "method": "get_resource_pages",
        "root_url": root_url
    }, indent=4, sort_keys=True))

    tree = get_page(root_url)
    for li in tree.find_all('li'):
        resource_link = li.find('a')
        top_level_resources[resource_link.string] = resource_link.get('href')

    logging.debug(json.dumps({
        "top_level_resources": top_level_resources
    }, indent=4, sort_keys=True))


def get_resource_subtypes():
    logging.info(json.dumps({
        "method": "get_resource_subtypes"
    }, indent=4, sort_keys=True))

    i = 0
    for resource_name, resource_page in top_level_resources.items():
        temp_subtypes = []
        logging.debug(json.dumps({
            "resource_name": resource_name,
            "resource_page": resource_page
        }, indent=4, sort_keys=True))

        tree = get_page(f'{BASE_URL}/{resource_page}')

        for li in tree.find_all('li', attrs={"class": "listitem"}):
            subtype_link = li.find('a')
            temp_subtypes.append({"name": subtype_link.string, "url": subtype_link.get('href')})

            logging.debug(json.dumps({
                "temp_subtypes": temp_subtypes
            }, indent=4, sort_keys=True))

        resource_subtypes[resource_name] = temp_subtypes
        logging.debug(json.dumps({
            "resource_subtypes": resource_subtypes
        }, indent=4, sort_keys=True))

        i += 1
        if MAX_PAGES_TO_PULL != 0 and i >= MAX_PAGES_TO_PULL:
            logging.warning('Reached Limit of pulled resources. Stopping process.')
            break


def text_cleanup(in_text):
    p1 = in_text.splitlines()
    p2 = [i.strip() for i in p1]
    return ' '.join(p2)


def collect_subtypes_for_resource():
    logging.info(json.dumps({
        "method": "collect_subtypes_for_resource"
    }, indent=4, sort_keys=True))

    for resource_name, resource_details in resource_subtypes.items():
        final_output = {}
        logging.debug(json.dumps({
            "resource_name": resource_name,
            "resource_details": resource_details
        }, indent=4, sort_keys=True))

        subtypes = []
        for resource_type in resource_details:
            logging.debug(json.dumps({
                "resource_type": resource_type
            }, indent=4, sort_keys=True))

            subtype_content = get_page(f'{BASE_URL}/{resource_type.get("url")}')

            subtype_description = subtype_content.find('div', id="main-col-body").find('p').get_text()

            subtype_yaml_head = resource_type.get('name').split('::')[-1] + ':\n  '
            subtype_yaml_string = subtype_content.find('code', class_="yaml").get_text()
            subtype_yaml_out = subtype_yaml_head + subtype_yaml_string.replace('\n', '\n  ')

            subtype_yaml = yaml.load(subtype_yaml_out, Loader=Loader)
            logging.debug(subtype_yaml)

            terms = []
            definitions = []
            subtype_properties = []
            try:
                subtype_variables = subtype_content.find('div', class_='variablelist').find('dl')
                for dts in subtype_variables.find_all('dt'):
                    terms.append(dts.get_text())
                for dds in subtype_variables.find_all('dd'):
                    definitions.append(dds.get_text())
            except AttributeError as aErr:
                logging.exception(f'There has been an error processing: {resource_type}.')
                logging.exception(f'aErr')

            for i in range(0, len(terms)):
                def_list = [j.strip() for j in definitions[i].splitlines()]
                def_list = list(filter(None, def_list))
                def_string = '\n'.join(def_list)
                subtype_properties.append({terms[i]: def_string})

            subtype_metadata = {
                'name': resource_type.get('name'),
                'description': text_cleanup(subtype_description),
                'properties': subtype_properties,
                'url': f'{BASE_URL}/{resource_type.get("url")}'
            }

            logging.debug(json.dumps({
                "subtype_description": subtype_description,
                "subtype_yaml": subtype_yaml,
                "subtype_properties": subtype_properties,
                "subtype_metadata": subtype_metadata
            }, indent=4, sort_keys=True))

            subtype_yaml.update({
                "MetaData": subtype_metadata
            })
            logging.debug(json.dumps(subtype_yaml, indent=4, sort_keys=True))
            subtypes.append(subtype_yaml)

        final_output[resource_name] = subtypes
        yaml_output = yaml.dump(json.loads(json.dumps(final_output)),
                                indent=2,
                                explicit_start=True,
                                explicit_end=True,
                                default_style=None,
                                default_flow_style=False,
                                line_break="+++",
                                allow_unicode=True,
                                width=100,
                                Dumper=Dumper)
        logging.debug(yaml_output)
        save_page(f'templates/{resource_name}.template', yaml_output)


def save_page(name=None, content=None):
    if name and content:
        logging.info(f'Saving file: {name}')
        with open(name, 'w') as file:
            file.write(content)
    else:
        logging.exception(f'Requested to save but name or content is empty.')
        raise Exception('Invalid file name or content.')


def remove_empty_lines(filename):
    logging.info(f'Cleaning file: {filename}')
    if not os.path.isfile(filename):
        logging.warning("{} does not exist ".format(filename))
        return False

    logging.debug(f'Opening file: {filename}')
    with open(filename) as filehandle:
        lines = filehandle.readlines()

    logging.debug(f'Cleaning file: {filename}')
    with open(filename, 'w') as filehandle:
        lines = filter(lambda x: x.strip(), lines)
        lines = [i.replace("''", '') for i in lines]
        filehandle.writelines(lines)


def cleanup_files():
    logging.info('Starting cleanup of files')
    for dirName, subdirList, fileList in os.walk(f'{TEMPLATE_DIR}'):
        for fname in fileList:
            logging.debug(f'Found file: {TEMPLATE_DIR}/{fname}')
            remove_empty_lines(f'{TEMPLATE_DIR}/{fname}')


def get_page(url=None):
    name = url.split('/')[-1]
    case_file = f'{TEMP_DIR}/{name}'
    try:
        logging.info(json.dumps({
            "method": "get_page",
            "url": url
        }, indent=4, sort_keys=True))

        if os.path.exists(case_file):
            logging.debug('Cache File Found.')
            with open(case_file, "r") as file:
                text = file.read()
            file.close()
        else:
            logging.debug('Fetching from online.')
            time.sleep(MIN_TIME_BETWEEN_REQUESTS)
            response = requests.get(url)
            text = response.text
        save_page(case_file, text)
        tree = BeautifulSoup(text, 'html.parser')
        return tree
    except HTTPError as http_error:
        logging.exception(f'Attempting to retrieve: {url}')
        logging.exception(f'Http error occurred: {http_error}')
    except Exception as err:
        logging.exception(f'Attempting to retrieve: {url}')
        logging.exception(f'Other Error occurred: {err}')


def main():
    get_resource_pages()
    get_resource_subtypes()
    collect_subtypes_for_resource()
    cleanup_files()


if __name__ == "__main__":
    main()
