import os
import sys
from shutil import copyfile
from xml.dom.minidom import parse
from xml.dom.minidom import parseString
import xml.etree.ElementTree as ET
import TestObjects
import mvn
from pom_file import Pom
from jcov_tracer import JcovTracer
from jcov_parser import JcovParser
from junitparser.junitparser import Error, Failure
import tempfile


class TestResult(object):
    def __init__(self, junit_test, suite_name=None):
        self.junit_test = junit_test
        self.classname = junit_test.classname or suite_name
        self.name = junit_test.name
        self.time = junit_test.time
        self.full_name = "{classname}.{name}".format(classname=self.classname, name=self.name)
        result = 'pass'
        if type(junit_test.result) is Error:
            result = 'error'
        if type(junit_test.result) is Failure:
            result = 'failure'
        self.outcome = result

    def __repr__(self):
        return "{full_name}: {outcome}".format(full_name=self.full_name, outcome=self.outcome)

    def is_passed(self):
        return self.outcome == 'pass'

    def get_observation(self):
        return 0 if self.is_passed() else 1

    def as_dict(self):
        return {'_tast_name': self.full_name, '_outcome': self.outcome}


class Repo(object):
    def __init__(self, repo_dir):
        self._repo_dir = repo_dir
        self.DEFAULT_ES_VERSION = '1.0.6'
        self.DEFAULT_SUREFIRE_VERSION = '2.17'
        self.DEFAULT_JUNIT_VERSION = '4.12'
        self.build_report = None

    @property
    def repo_dir(self):
        return self._repo_dir

    # Executes mvn test
    def install(self, module=None, testcases=[], time_limit=sys.maxint, debug=False, tests_to_run=None, env=None):
        self.change_surefire_ver()
        inspected_module = self.repo_dir
        if module is not None:
            inspected_module = module
        install_cmd = self.generate_mvn_install_cmd(module=inspected_module, testcases=testcases, debug=debug, tests_to_run=tests_to_run)
        build_report = mvn.wrap_mvn_cmd(install_cmd, time_limit=time_limit, dir=self._repo_dir, env=env)
        return build_report

    # Executes mvn test
    def test(self, module=None, tests=[], time_limit=sys.maxint):
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        test_cmd = self.generate_mvn_test_cmd(module=inspected_module, tests=tests)
        build_report = mvn.wrap_mvn_cmd(test_cmd, time_limit=time_limit)
        return build_report

    # Generates tests. As for now implemented with evosuite
    def generate_tests(self, module=None, classes=[], time_limit=sys.maxint):
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        if not self.tests_generator_setup(inspected_module):
            self.setup_tests_generator(inspected_module)
        test_cmd = self.generate_mvn_generate_tests_cmd(module=inspected_module, classes=classes)
        build_report = mvn.wrap_mvn_cmd(test_cmd, time_limit=time_limit)
        if os.path.exists(os.path.join(self.repo_dir, 'cutsFile.txt')):
            os.remove(os.path.join(self.repo_dir, 'cutsFile.txt'))
        return build_report

    # Executes mvn clean
    def clean(self, module=None):
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        test_cmd = self.generate_mvn_clean_cmd(inspected_module)
        build_report = mvn.wrap_mvn_cmd(test_cmd)
        return build_report

    # Executes mvn clean
    def site(self, module=None):
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        build_report = mvn.wrap_mvn_cmd(self.generate_mvn_site_cmd(inspected_module))
        return build_report

    # Executes mvn compile
    def test_compile(self, module=None):
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        test_cmd = self.generate_mvn_test_compile_cmd(inspected_module)
        self.build_report = mvn.wrap_mvn_cmd(test_cmd)
        return self.build_report

    def get_test_results(self):
        from junitparser import JUnitXml
        from junitparser.junitparser import Error, Failure
        SURFIRE_DIR_NAME = 'surefire-reports'

        def get_surefire_files():
            surefire_files = []
            for root, _, files in os.walk(self._repo_dir):
                for name in files:
                    if name.endswith('.xml') and os.path.basename(root) == SURFIRE_DIR_NAME:
                        surefire_files.append(os.path.join(root, name))
            return surefire_files

        class Test(object):
            def __init__(self, junit_test):
                self.junit_test = junit_test
                self.classname = junit_test.classname
                self.name = junit_test.name
                self.full_name = "{classname}@{name}".format(classname=self.classname, name=self.name).lower()
                result = 'pass'
                if type(junit_test.result) is Error:
                    result = 'error'
                if type(junit_test.result) is Failure:
                    result = 'failure'
                self.outcome = result

            def __repr__(self):
                return "{full_name}: {outcome}".format(full_name=self.full_name, outcome=self.outcome)

            def is_passed(self):
                return self.outcome == 'pass'

            def get_observation(self):
                return 0 if self.is_passed() else 1

            def as_dict(self):
                return {'_tast_name': self.full_name, '_outcome': self.outcome}

        outcomes = {}
        for report in get_surefire_files():
            try:
                for case in JUnitXml.fromfile(report):
                    test = Test(case)
                    outcomes[test.full_name] = test
            except:
                pass
        return outcomes

    # Returns tests reports objects currently exists in this repo in path_to_reports
    def parse_tests_reports(self, path_to_reports, module=None):
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        ans = []
        for filename in os.listdir(path_to_reports):
            if filename.endswith(".xml"):
                ans.append(TestObjects.TestClassReport(os.path.join(path_to_reports, filename), inspected_module))
        return ans

    # Gets path to tests object in repo, or in a cpsecifc module if specified
    def get_tests(self, module=None):
        ans = []
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        if os.path.isdir(inspected_module + '\\src\\test'):
            if os.path.isdir(inspected_module + '\\src\\test\\java'):
                ans.extend(mvn.parse_tests(inspected_module + '\\src\\test\\java'))
            else:
                ans.extend(mvn.parse_tests(inspected_module + '\\src\\test'))
        for filename in os.listdir(inspected_module):
            file_abs_path = os.path.join(inspected_module, filename)
            if os.path.isdir(file_abs_path):
                if not (filename == 'src' or filename == '.git'):
                    ans.extend(self.get_tests(file_abs_path))
        return ans

    # Gets all the reports in the given module if given, else in the given module
    def get_tests_reports(self, module=None):
        ans = []
        inspected_module = self.repo_dir
        if not module == None:
            inspected_module = module
        path_to_reports = os.path.join(inspected_module, 'target\\surefire-reports')
        if os.path.isdir(path_to_reports):
            ans.extend(self.parse_tests_reports(path_to_reports, inspected_module))
        for filename in os.listdir(inspected_module):
            file_abs_path = os.path.join(inspected_module, filename)
            if os.path.isdir(file_abs_path):
                if not (filename == 'src' or filename == '.git'):
                    ans.extend(self.get_tests_reports(file_abs_path))
        return ans

    # Adds Tracer agent to surefire. Outpur of tracer goes to target
    def setup_tracer(self, target=None):
        agent_path_src = os.path.join(mvn.tracer_dir, r'target\uber-tracer-1.0.1-SNAPSHOT.jar')
        if not os.path.isfile(agent_path_src):
            os.system('mvn install -f {}'.format(mvn.tracer_dir))
        agent_path_dst = os.path.join(self.repo_dir, 'agent.jar')
        paths_path = os.path.join(self.repo_dir, 'paths.txt')
        copyfile(agent_path_src, agent_path_dst)
        with open(paths_path, 'w+') as paths:
            paths.write(Repo.get_mvn_repo() + '\n')
            paths.write(self.repo_dir)
        self.add_argline_to_surefire('-javaagent:{}={}'.format(agent_path_dst, paths_path))

    @staticmethod
    def get_mvn_repo():
        return os.path.join(os.environ['USERPROFILE'], '.m2\\repository')

    def setup_jcov_tracer(self, path_to_classes_file=None, path_to_out_template=None, target_dir=None, class_path=None,
                          instrument_only_methods=True):
        result_file = "result.xml"
        if target_dir:
            result_file = os.path.join(target_dir, result_file)
        jcov = JcovTracer(self.repo_dir, path_to_out_template, path_to_classes_file, result_file, class_path=class_path,
                          instrument_only_methods=instrument_only_methods)
        for pom_file in self.get_all_pom_paths(self._repo_dir):
            pom = Pom(pom_file)
            for value in jcov.get_values_to_add():
                pom.add_pom_value(value)
        return jcov

    def has_surefire(self):
        for pom_file in self.get_all_pom_paths(self._repo_dir):
            pom = Pom(pom_file)
            if pom.has_surefire():
                return True
        return False

    def run_under_jcov(self, target_dir, debug=False, instrument_only_methods=True, short_type=True, module=None, tests_to_run=None, check_comp_error=True, classes_to_trace=None):
        self.test_compile()
        if check_comp_error and mvn.has_compilation_error(self.build_report):
            return []
        f, path_to_classes_file = tempfile.mkstemp()
        os.close(f)
        f, path_to_template = tempfile.mkstemp()
        os.close(f)
        os.remove(path_to_template)
        jcov = self.setup_jcov_tracer(path_to_classes_file, path_to_template, target_dir=target_dir, class_path=Repo.get_mvn_repo(), instrument_only_methods=instrument_only_methods)
        jcov.execute_jcov_process(debug=debug)
        if classes_to_trace:
            with open(path_to_classes_file, "wb") as f:
                f.writelines(classes_to_trace)
        self.build_report = self.install(debug=debug, module=module, tests_to_run=tests_to_run)
        jcov.stop_grabber()
        os.remove(path_to_classes_file)
        os.remove(path_to_template)
        return JcovParser(target_dir, instrument_only_methods, short_type).parse()

    # Changes all the pom files in a module recursively
    def get_all_pom_paths(self, module=None):
        ans = []
        inspected_module = self.repo_dir
        if module is not None:
            inspected_module = module
        pom_path = os.path.join(inspected_module, 'pom.xml')
        if os.path.isfile(pom_path):
            try:
                parse(pom_path)
                ans.append(pom_path)
            except:
                pass
        for file in os.listdir(inspected_module):
            full_path = os.path.join(inspected_module, file)
            if os.path.isdir(full_path):
                ans.extend(self.get_all_pom_paths(full_path))
        return ans

    # Changes surefire version in a pom
    def change_surefire_ver(self, version="2.18.1", module=None):
        ans = []
        inspected_module = self.repo_dir
        if module is not None:
            inspected_module = module
        poms = self.get_all_pom_paths(inspected_module)
        new_file_lines = []
        for pom in poms:
            try:
                xmlFile = parse(pom)
            except:
                pass
                # assume that file is not valid pom
            tmp_build_list = xmlFile.getElementsByTagName('build')
            build_list = list(
                filter(lambda b: not b.parentNode == None and b.parentNode.localName == 'project', tmp_build_list))
            if len(build_list) == 0:
                continue
            assert len(build_list) == 1
            plugins_tags = build_list[0].getElementsByTagName('plugins')
            if len(plugins_tags) == 0:
                continue
            for plugins_tag in plugins_tags:
                if plugins_tag.parentNode.localName == 'build':
                    artifacts_ids = list(
                        map(lambda a: str(a.firstChild.data), plugins_tag.getElementsByTagName('artifactId')))
                    if not any(a_id == 'maven-surefire-plugin' for a_id in artifacts_ids):
                        new_plugin = plugins_tag.ownerDocument.createElement(tagName='plugin')
                        new_group_id = new_plugin.ownerDocument.createElement(tagName='groupId')
                        new_artifact_id = new_plugin.ownerDocument.createElement(tagName='artifactId')
                        new_group_id_text = new_group_id.ownerDocument.createTextNode('org.apache.maven.plugins')
                        new_artifact_id_text = new_artifact_id.ownerDocument.createTextNode('maven-surefire-plugin')
                        new_group_id.appendChild(new_group_id_text)
                        new_plugin.appendChild(new_group_id)
                        new_artifact_id.appendChild(new_artifact_id_text)
                        new_plugin.appendChild(new_artifact_id)
                        plugins_tag.appendChild(new_plugin)
            for plugins_tag in plugins_tags:
                mvn.change_plugin_version_if_exists(plugins_tag, 'maven-surefire-plugin', version)
            os.remove(pom)
            with open(pom, 'w+') as f:
                tmp_str = xmlFile.toprettyxml()
                copy_tmp_str = ''
                for char in tmp_str[::]:
                    if 125 < ord(char):
                        copy_tmp_str += 'X'
                    else:
                        copy_tmp_str += char
                lines = list(filter(lambda line: len(line) > 0, copy_tmp_str.split('\n')))
                for line in lines:
                    if not (all(c == ' ' for c in line) or all(c == '\t' for c in line)):
                        f.write(line + '\n')

    # Changes surefire version in a pom
    def add_argline_to_surefire(self, content):
        inspected_module = self.repo_dir
        poms = self.get_all_pom_paths(inspected_module)
        for pom in poms:
            xmlFile = parse(pom)
            tmp_build_list = xmlFile.getElementsByTagName('build')
            build_list = list(
                filter(lambda b: not b.parentNode == None and b.parentNode.localName == 'project', tmp_build_list))
            if len(build_list) == 0:
                continue
            assert len(build_list) == 1
            plugins_tags = build_list[0].getElementsByTagName('plugins')
            if len(plugins_tags) == 0:
                continue
            for plugins_tag in plugins_tags:
                if plugins_tag.parentNode.localName == 'build':
                    artifacts_ids = list(
                        map(lambda a: str(a.firstChild.data), plugins_tag.getElementsByTagName('artifactId')))
                    if not any(a_id == 'maven-surefire-plugin' for a_id in artifacts_ids):
                        new_plugin = plugins_tag.ownerDocument.createElement(tagName='plugin')
                        new_group_id = new_plugin.ownerDocument.createElement(tagName='groupId')
                        new_artifact_id = new_plugin.ownerDocument.createElement(tagName='artifactId')
                        new_group_id_text = new_group_id.ownerDocument.createTextNode('org.apache.maven.plugins')
                        new_artifact_id_text = new_artifact_id.ownerDocument.createTextNode('maven-surefire-plugin')
                        new_group_id.appendChild(new_group_id_text)
                        new_plugin.appendChild(new_group_id)
                        new_artifact_id.appendChild(new_artifact_id_text)
                        new_plugin.appendChild(new_artifact_id)
                        plugins_tag.appendChild(new_plugin)
            for plugins_tag in plugins_tags:
                mvn.add_plugin_configuration_argline(plugins_tag, 'maven-surefire-plugin', content=content)
            os.remove(pom)
            with open(pom, 'w+') as f:
                tmp_str = xmlFile.toprettyxml()
                copy_tmp_str = ''
                for char in tmp_str[::]:
                    if 125 < ord(char):
                        copy_tmp_str += 'X'
                    else:
                        copy_tmp_str += char
                lines = list(filter(lambda line: len(line) > 0, copy_tmp_str.split('\n')))
                for line in lines:
                    if not (all(c == ' ' for c in line) or all(c == '\t' for c in line)):
                        f.write(line + '\n')

    def add_element_to_pom(self, pom_path, path, path_filter, element_name, element_value, add_new_element=True):
        """
        add element to pom file, used to modify the surefire plugin
        :param pom_path: the path to the pom.xml to modify
        :param path: the path to the element in the pom.xml (list of strings)
        :param element_name: name of the element to add
        :param element_value: the value to add
        :param add_new_element: if True add new element, else append to existing element
        """
        xml.etree.ElementTree.register_namespace('', "http://maven.apache.org/POM/4.0.0")
        xml.etree.ElementTree.register_namespace('xsi', "http://www.w3.org/2001/XMLSchema-instance")

        def get_children_by_name(element, name):
            return filter(lambda e: e.tag.endswith(name), element.getchildren())

        def get_or_create_child(element, name):
            child = get_children_by_name(element, name)
            if len(child) == 0:
                return xml.etree.ElementTree.SubElement(element, name)
            else:
                return child[0]

        et = xml.etree.ElementTree.parse(pom_path)
        path = ['build', 'plugins', 'plugin']
        elements = et.getroot()
        for name in path:
            elements = reduce(list.__add__, map(lambda elem: get_children_by_name(elem, name), elements), [])
        surfire_plugins = filter(lambda plugin: filter(lambda x: x.text == "maven-surefire-plugin",
                                                       get_children_by_name(plugin, "artifactId")),
                                 filter(lambda e: e.tag.endswith('plugin'), et.getroot().iter()))

        pass

    def run_function_on_poms_by_filter(self, pom_filter, function, *args, **kwargs):
        map(lambda pom: function(pom, *args, **kwargs), filter(pom_filter, self.get_all_pom_paths(self._repo_dir)))

    # Returns mvn command string that runns the given tests in the given module
    def generate_mvn_test_cmd(self, tests, module=None):
        mvn_names = list(map(lambda t: t.mvn_name, tests))
        if module == None or module == self.repo_dir:
            ans = 'mvn test -fn'
        else:
            ans = 'mvn -pl :{} -am test -fn'.format(
                os.path.basename(module))
        # ans = 'mvn test surefire:test -DfailIfNoTests=false -Dmaven.test.failure.ignore=true -Dtest='
        ans += ' -DfailIfNoTests=false'
        if len(mvn_names) > 0:
            ans += ' -Dtest='
            for mvn_name in mvn_names:
                if not ans.endswith('='):
                    ans += ','
                ans += mvn_name
        ans += ' -f ' + self.repo_dir
        return ans

    # Returns mvn command string that generates tests for the given module
    def generate_mvn_generate_tests_cmd(self, classes, module=None):
        if module == None or module == self.repo_dir:
            ans = 'mvn evosuite:generate evosuite:export -fn'
        else:
            ans = 'mvn -pl :{} -am evosuite:generate -fn'.format(
                os.path.basename(module))
        if len(classes) > 0:
            path_to_cutsfile = os.path.join(self.repo_dir,"cutsFile.txt")
            with open(path_to_cutsfile , "w+") as tmp_file:
                tmp_file.write(' ,'.join(classes))
                ans += ' '
                ans += ' -DcutsFile="{}"'.format(path_to_cutsfile)
        ans += ' -f ' + self.repo_dir
        return ans

    # Returns mvn command string that runns the given tests in the given module
    def generate_mvn_install_cmd(self, testcases, module=None, debug=False, tests_to_run=None):
        testclasses = []
        for testcase in testcases:
            if not testcase.parent in testclasses:
                testclasses.append(testcase.parent)
        if module == None or module == self.repo_dir:
            ans = 'mvn install -fn -Drat.skip=true -Drat.ignoreErrors=true -Drat.numUnapprovedLicenses=10000 -Djacoco.skip=true  -DfailIfNoTests=false'
        else:
            ans = 'mvn -pl :{} -am install -Drat.skip=true -Drat.ignoreErrors=true -Drat.numUnapprovedLicenses=10000 -Djacoco.skip=true -fn'.format(
                os.path.basename(module))
        # ans = 'mvn test surefire:test -DfailIfNoTests=false -Dmaven.test.failure.ignore=true -Dtest='
        ans += ' -DfailIfNoTests=false'
        if debug:
            ans += ' -Dmaven.surefire.debug="-Xdebug -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=8000 -Xnoagent -Djava.compiler=NONE"'
        if tests_to_run:
            ans += " -Dtest="
            ans += ','.join(tests_to_run)
        if len(testcases) > 0:
            ans += ' -Dtest='
            for testclass in testclasses:
                if not ans.endswith('='):
                    ans += ','
                ans += testclass.mvn_name
        # ans += ' -f ' + self.repo_dir
        return ans

    # Returns mvn command string that compiles the given the given module
    def generate_mvn_test_compile_cmd(self, module):
        if module == self.repo_dir:
            ans = 'mvn test-compile -fn  -Drat.skip=true -Drat.ignoreErrors=true -Drat.numUnapprovedLicenses=10000'
        else:
            ans = 'mvn -pl :{} -am test-compile -fn  -Drat.skip=true -Drat.ignoreErrors=true -Drat.numUnapprovedLicenses=10000'.format(
                os.path.basename(module))
        ans += ' -f ' + self.repo_dir
        return ans

    # Returns mvn command string that cleans the given the given module
    def generate_mvn_clean_cmd(self, module):
        if module == self.repo_dir:
            ans = 'mvn clean '
        else:
            ans = 'mvn -pl :{} -am clean -fn'.format(
                os.path.basename(module))
        ans += ' -f ' + self.repo_dir
        return ans

    def generate_mvn_site_cmd(self, module):
        return 'mvn site -f {0} -fn '.format(module)

    # Returns mvn command string that prints evosuite help material
    def generate_mvn_evosuite_help_cmd(self, module):
        if module == self.repo_dir:
            ans = 'mvn evosuite:help '
        else:
            ans = 'mvn -pl :{} -am mvn evosuite:help -fn'.format(
                os.path.basename(module))
        ans += ' -f ' + self.repo_dir
        return ans

    # Add tags to the pom. xquey is a string written in xpath aka xquery convention
    # Behaviour is unknown if the xquery doesn't refer to a single tag
    def set_pom_tag(self, xquery, value, module='', create_if_not_exist=False):
        pom = self.get_pom(module)
        root = ET.parse(pom).getroot()
        xmlns, _ = mvn.tag_uri_and_name(root)
        if not xmlns == '':
            tmp_tags_1 = xquery.split('/')
            tmp_tags_2 = list(map(lambda t: self.add_xmlns_prefix(xmlns, t), tmp_tags_1))
            tags = list(map(lambda t: self.clean_query_string(t), tmp_tags_2))
        tag = self.get_tag(root, tags[1:], create_if_not_exist=create_if_not_exist)
        tag.text = value
        self.rewrite_pom(root=root, module=module)

    # Gets the tag specified in the xquery
    def get_pom_tag(self, xquery, module=''):
        pom = self.get_pom(module)
        root = ET.parse(pom).getroot()
        xmlns, _ = mvn.tag_uri_and_name(root)
        if not xmlns == '':
            tmp_tags_1 = xquery.split('/')
            tmp_tags_2 = list(map(lambda t: self.add_xmlns_prefix(xmlns, t), tmp_tags_1))
            tags = list(map(lambda t: self.clean_query_string(t), tmp_tags_2))
        return self.get_tag(root, tags[1:])

    # Recursively add element to tag
    def get_tag(self, root_tag, subtags_path_array, create_if_not_exist=False):
        if len(subtags_path_array) == 0:
            return root_tag
        next_tag_list = root_tag.findall(subtags_path_array[0])
        if len(next_tag_list) == 0:
            if create_if_not_exist:
                condition = ''
                tag_and_cond = subtags_path_array[0].replace(']', '').split('[')
                tag_name = tag_and_cond[0]
                if len(tag_and_cond) > 1:
                    condition = tag_and_cond[1]
                new_tag = ET.SubElement(root_tag, tag_name)
                if not condition == '':
                    [elem_name, val] = condition.split('=')
                    new_tag_attr = ET.SubElement(new_tag, elem_name)
                    new_tag_attr.text = val.strip('\'')
                return self.get_tag(root_tag=new_tag, subtags_path_array=subtags_path_array[1:],
                                    create_if_not_exist=create_if_not_exist)
            else:
                return None
        if len(next_tag_list) > 1:
            return None
        next_tag = next_tag_list[0]
        return self.get_tag(root_tag=next_tag, subtags_path_array=subtags_path_array[1:],
                            create_if_not_exist=create_if_not_exist)

    def rewrite_pom(self, root, module=''):
        pom = os.path.join(module, 'pom.xml')
        rough_string = ET.tostring(root, 'utf-8')
        reparsed = parseString(rough_string).toprettyxml().replace('</ns0:', '</').replace('<ns0:', '<')
        os.remove(pom)
        with open(pom, 'w+') as f:
            tmp_str = reparsed
            copy_tmp_str = ''
            for char in tmp_str[::]:
                if 125 < ord(char):
                    copy_tmp_str += 'X'
                else:
                    copy_tmp_str += char
            lines = list(filter(lambda line: len(line) > 0, copy_tmp_str.split('\n')))
            for line in lines:
                if not (all(c == ' ' for c in line) or all(c == '\t' for c in line)):
                    f.write(line + '\n')

    def observe_tests(self):
        from junitparser import JUnitXml, junitparser
        outcomes = {}
        for report in self.get_surefire_files():
            try:
                suite = JUnitXml.fromfile(report)
                for case in suite:
                    test = TestResult(case, suite.name)
                    outcomes[test.full_name.lower()] = test
            except Exception as e:
                pass
        return outcomes

    def get_surefire_files(self):
        SURFIRE_DIR_NAME = 'surefire-reports'
        surefire_files = []
        for root, _, files in os.walk(self.repo_dir):
            for name in files:
                if name.endswith('.xml') and os.path.basename(root) == SURFIRE_DIR_NAME:
                    surefire_files.append(os.path.join(root, name))
        return surefire_files

    # Returns the dictionary that map testcase string to its traces strings
    def get_traces(self, testcase_name=''):
        ans = {}
        debugger_tests_dir = os.path.relpath(os.path.join(self.repo_dir, r'../../DebuggerTests'))
        if not os.path.isdir(debugger_tests_dir):
            return ans
        for filename in os.listdir(debugger_tests_dir):
            if (filename.startswith('Trace_') or filename.endswith(".txt")) and testcase_name.replace('#',
                                                                                                      '@') in filename:
                with open(os.path.join(debugger_tests_dir, filename), 'r') as file:
                    key = filename.replace('.txt', '')
                    ans[key] = []
                    tmp = file.readlines()
                    for trace in tmp:
                        function_name = trace.replace('@', '#').replace('\n', '').split(' ')[-1]
                        if not function_name in ans[key]:
                            ans[key].append(str(function_name))
        return ans

    # Returns the dictionary that map testcase string to its traces strings
    def get_trace(self, testcase_name):
        ans = []
        dict = self.get_traces(testcase_name=testcase_name)
        if not len(dict) == 1:
            return ans
        ans = dict[dict.keys()[0]]
        return ans

    # Returns the pom path associated with the given module
    def get_pom(self, module):
        if module == '':
            module = self.repo_dir
        pom_singelton = list(
            filter(lambda f: f == 'pom.xml', os.listdir(module))
        )
        if not len(pom_singelton) == 1:
            return ''
        else:
            return os.path.join(module, pom_singelton[0])

    # Adds the xmlns prefix to the tag
    def add_xmlns_prefix(self, xmlns, tag):
        prefix = '{' + xmlns + '}'
        with_prefix = ''
        if tag == '.':
            return tag
        if tag.startswith(prefix):
            with_prefix = tag
        else:
            with_prefix = prefix + tag
        if with_prefix.find('[') < with_prefix.find(']'):
            [tag_name, condition] = with_prefix.split('[')
            condition = condition.replace(']', '')
            [elem_name, val] = condition.split('=')
            elem_with_prefix = self.add_xmlns_prefix(xmlns, elem_name)
            with_prefix = tag_name + '[' + elem_with_prefix + '=' + val + ']'
        return with_prefix

    # Removes redundant chars from the given query to validate it
    def clean_query_string(self, xquery):
        ans = xquery
        while ' = ' in ans or ' =' in ans or '= ' in ans:
            ans = ans.replace(' = ', '=')
            ans = ans.replace(' =', '=')
            ans = ans.replace('= ', '=')
        return ans

    # Returns true if self has tests generator setup
    def tests_generator_setup(self, module):
        mvn_help_cmd = self.generate_mvn_evosuite_help_cmd(module)
        EVOUSUITE_CONFIGURED_INDICATION = 'evosuite:generate'
        with os.popen(mvn_help_cmd) as proc:
            tmp_file_path = 'tmp_file.txt'
            with open(tmp_file_path, "w+") as tmp_file:
                mvn.duplicate_stdout(proc, tmp_file)
            with open(tmp_file_path, "r") as tmp_file:
                mvn.duplicate_stdout(proc, tmp_file)
                build_report = tmp_file.readlines()
            return any(list(map(lambda l: EVOUSUITE_CONFIGURED_INDICATION in l, build_report)))

    def setup_tests_generator(self, module):
        evousuite_version_property_xquery = '/'.join(['.','properties','evosuiteVersion'])
        self.set_pom_tag(xquery=evousuite_version_property_xquery, create_if_not_exist=True, module=module,
                         value=self.DEFAULT_ES_VERSION)
        self.add_plugin(artifactId='evosuite-maven-plugin', groupId='org.evosuite.plugins',
                        version='${evosuiteVersion}', module=module)
        self.add_plugin(artifactId='maven-surefire-plugin', groupId='org.apache.maven.plugins',
                        version=self.DEFAULT_SUREFIRE_VERSION, module=module)
        self.add_dependency(artifactId='evosuite-standalone-runtime', groupId='org.evosuite',
                            version='${evosuiteVersion}', module=module)
        self.add_dependency(artifactId='junit', groupId='junit',
                            version=self.DEFAULT_JUNIT_VERSION, module=module)
        evousuite_xpath = r"./build/plugins/plugin[artifactId = 'evosuite-maven-plugin']"
        surefire_xpath = r"./build/plugins/plugin[artifactId = 'maven-surefire-plugin']"
        execution_xpath = "executions/execution"
        prepare_goal_xquery = '/'.join([evousuite_xpath, execution_xpath, "goals/goal"])
        phase_xquery = '/'.join([evousuite_xpath, execution_xpath, "phase"])
        listener_name_xquery = '/'.join([surefire_xpath, 'configuration', 'properties', 'property', 'name'])
        listener_value_xquery = '/'.join([surefire_xpath, 'configuration', 'properties', 'property', 'value'])
        self.set_pom_tag(xquery=prepare_goal_xquery, create_if_not_exist=True, module=module, value='prepare')
        self.set_pom_tag(xquery=phase_xquery, create_if_not_exist=True, module=module, value='process-test-classes')
        self.set_pom_tag(xquery=listener_name_xquery, create_if_not_exist=True, module=module, value='listener')
        self.set_pom_tag(xquery=listener_value_xquery, create_if_not_exist=True, module=module,
                         value='org.evosuite.runtime.InitializingListener')

    def add_plugin(self, artifactId, groupId, version, module):
        plugin_xpath = r"./build/plugins/plugin[artifactId = '{}']".format(artifactId)
        set_groupId_xquery = '/'.join([plugin_xpath, "groupId"])
        set_version_xquery = '/'.join([plugin_xpath, "version"])
        self.set_pom_tag(xquery=set_groupId_xquery, create_if_not_exist=True, module=module, value=groupId)
        self.set_pom_tag(xquery=set_version_xquery, create_if_not_exist=True, module=module, value=version)

    def add_dependency(self, artifactId, groupId, version, module):
        dependency_xpath = r"./dependencies/dependency[artifactId = '{}']".format(artifactId)
        set_groupId_xquery = '/'.join([dependency_xpath, "groupId"])
        set_version_xquery = '/'.join([dependency_xpath, "version"])
        self.set_pom_tag(xquery=set_groupId_xquery, create_if_not_exist=True, module=module, value=groupId)
        self.set_pom_tag(xquery=set_version_xquery, create_if_not_exist=True, module=module, value=version)

    def add_javadoc(self):
        from javadoc import JavaDoc
        for pom_file in self.get_all_pom_paths(self._repo_dir):
            pom = Pom(pom_file)
            pom.set_site_version()
            for value in JavaDoc.get_pom_values():
                pom.add_pom_value(value, create_plugin_if_not_exists=True)
            pom.save()

    def javadoc_command(self, dump_path=None):
        from javadoc import JavaDoc
        import json
        jsons = JavaDoc.get_dir_javadoc(self._repo_dir)
        if dump_path:
            with open(dump_path, "wb") as f:
                json.dump(jsons, f)
        return jsons


if __name__ == "__main__":
    repo = Repo(r"Z:\component_importance\WAGON\clones\217")
    t = list(repo.run_under_jcov(r"c:\temp\trace"))
    exit()
    # repo = Repo(r"C:\amirelm\projects_minors\JEXL\version_to_test_trace\repo")
    # obs = repo.observe_tests()
    # pass
    # traces = JcovParser(r"C:\temp\traces").parse()
    # import time
    # import os
    # import gc
    # import git
    # import json
    #
    # def mkdir(path):
    #     if not os.path.exists(path):
    #         os.mkdir(path)
    #     return path
    #
    # def dump(obj, file_name):
    #     with open(file_name+".json", "wb") as f:
    #         json.dump(obj, f)
    #
    # base_path = mkdir(r"C:\amirelm\component_importnace\data\rotem_lang\clones")
    # traces_path = mkdir(r"C:\amirelm\component_importnace\data\rotem_lang\traces")
    # traces_json_path = mkdir(r"C:\amirelm\component_importnace\data\rotem_lang\traces_json")
    # call_graphs = mkdir(r"C:\amirelm\component_importnace\data\rotem_lang\call_graphs")
    # execution_graphs = mkdir(r"C:\amirelm\component_importnace\data\rotem_lang\execution_graphs")
    # obs_path = mkdir(r"C:\amirelm\component_importnace\data\rotem_lang\observations")
    # #interesting = ["0aa57f04ede369a4f813bbb86d3eac1ed20b084c", "0cc451d5e5cb565eb7311308466f487bc534ebaf", "19f33e4e0d824e732d07f06a08567c27b3c808f3", "1c606c3d96838e595a0664cbafdd60caae34aa0e", "229151ec41339450e4d4f857bf92ed080d3e2430", "38f8bcc60b90295f0a697f32e760a0082571bc09", "3905071819a14403d1cdb9437d2e005adf18fc70", "3b46d611b2d595131ce0bce9bdb3209c55391be7", "3cea4b2af3f9caf6aa72fa56d647c513d320e073", "3f900a7395e31eaa72e0fa2fb43c090e5a8fa4ed", "48bf241d4149919e0928e39616bee2e3783e2987", "5209cefa81c9c48a34e5472fdcf2a308a4da2589", "575be16474e8e8246d4bbde6f243fdf38c34ad5b", "5ccddb3ff7c65882ad6bbf95cbdac9debc76a871", "68217617c54467c7c6098168e714a2fb6a48847d", "7d1b54b33b07a570060824a703222a77c35b1fa0", "8185a5f63e23be852d600a80daa5b848fa836a65", "8da5fb28a764eee26c76a5018c293f224017887b", "ac2a39e92a71d5f9eb3ca7c6cc789b6341c582a4", "ac58807ede6d9a0625b489cdca6fd37bad9cacfe", "b2f1757bf9ec1632a940b9a2e65a1a022ba54af8", "b5906d3f325ca3a1147d5fa68912975e2e6c347e", "b6f7a8a8be57c9525c59e9f21e958e76cee0dbaf", "c71373047dc2172b0f06cebf61da284323d6ff99", "cbf8e4eb017a99af9a8f24eb8429e8a12b62af8b", "cf28c89dcf72d27573c478eb91e3b470de060edd", "cfff06bead88e2c1bb164285f89503a919e0e27f", "d8c22b8e1c8592bc8c6f6169a5b090082969acd4", "e28c95ac2ce95852add84bdf3d2d9c00ac98f5de", "ec0c4e5508dbd8af83253f7c50f8b728a1003388"]
    # for dir in os.listdir(base_path):
    #     try:
    #         gc.collect()
    #         repo_path = os.path.join(base_path, dir)
    #         repo = Repo(repo_path)
    #         git.Repo(repo_path).git.checkout('--', '.')
    #         repo.clean()
    #         traces_dir = mkdir(os.path.join(traces_path, dir))
    #         # traces = repo.run_under_jcov(traces_dir, False, instrument_only_methods=True)
    #         traces = JcovParser(traces_dir).parse()
    #         import networkx
    #         for trace in traces:
    #             g = networkx.DiGraph()
    #             g.add_edges_from(trace.get_execution_edges())
    #             execution = mkdir(os.path.join(execution_graphs, dir))
    #             networkx.write_gexf(g, os.path.join(execution, trace.test_name + ".gexf"))
    #             g = networkx.DiGraph()
    #             call = mkdir(os.path.join(call_graphs, dir))
    #             g.add_edges_from(trace.get_call_graph_edges())
    #             networkx.write_gexf(g, os.path.join(call, trace.test_name + ".gexf"))
    #             json_trace = os.path.join(mkdir(os.path.join(traces_json_path, dir)), trace.test_name)
    #             dump(trace.get_trace(), json_trace)
    #         obs = repo.observe_tests()
    #         dump(map(lambda x: x.as_dict(), obs.values()), os.path.join(obs_path, dir))
    #     except:
    #         pass
    #
    # start = time.time()
    # print "start time:", start
    # # repo = Repo(r"C:\Temp\bugs-dot-jar\accumulo")
    # # repo.add_javadoc()
    # # repo.site()
    # # exit()
    # jsons = repo.javadoc_command(r"c:\temp\jsons.json")
    # exit()
    import os
    repos_dir = r"Z:\ev_repos"
    traces_dir = r"Z:\ev_traces"
    skip = ["math", "ABDERA".lower()]
    for d in os.listdir(repos_dir):
        if d.lower() in skip:
            continue
        try:
            repo = Repo(os.path.join(repos_dir, d))
            if not os.path.exists(os.path.join(traces_dir, d)):
                os.mkdir(os.path.join(traces_dir, d))
            traces = repo.run_under_jcov(os.path.join(traces_dir, d), False, instrument_only_methods=False)
        except:
            pass
    # obs = repo.observe_tests()
    # import networkx
    # for trace in traces:
    #     g = networkx.DiGraph()
    #     g.add_edges_from(traces[trace].get_execution_edges())
    #     networkx.write_gexf(g, os.path.join(r"C:\Temp\trace_grpahs", trace + "_execution.gexf"))
    #     g = networkx.DiGraph()
    #     g.add_edges_from(traces[trace].get_call_graph_edges())
    #     networkx.write_gexf(g, os.path.join(r"C:\Temp\trace_grpahs", trace + "_call_graph.gexf"))
    # print "end time:", time.time() - start
