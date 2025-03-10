# coding=utf-8
"""Tests related to repository versions."""
import unittest
from random import choice, randint, sample
from time import sleep
from urllib.parse import urlsplit

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import ARTIFACTS_PATH
from pulp_smash.pulp3.utils import (
    delete_orphans,
    delete_version,
    gen_repo,
    gen_distribution,
    get_added_content,
    get_added_content_summary,
    get_artifact_paths,
    get_content,
    get_content_summary,
    get_removed_content,
    get_removed_content_summary,
    get_versions,
    modify_repo,
    sync,
)
from requests.exceptions import HTTPError

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE2_FIXTURE_MANIFEST_URL,
    FILE_CONTENT_NAME,
    FILE_CONTENT_PATH,
    FILE_DISTRIBUTION_PATH,
    FILE_FIXTURE_COUNT,
    FILE_FIXTURE_MANIFEST_URL,
    FILE_FIXTURE_SUMMARY,
    FILE_LARGE_FIXTURE_MANIFEST_URL,
    FILE_MANY_FIXTURE_MANIFEST_URL,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    create_file_publication,
    gen_file_remote,
    populate_pulp,
)
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa
from pulpcore.tests.functional.api.using_plugin.utils import skip_if


def remove_created_key(dic):
    """Given a dict remove the key `created`."""
    return {k: v for k, v in dic.items() if k != 'created'}


class AddRemoveContentTestCase(unittest.TestCase):
    """Add and remove content to a repository. Verify side-effects.

    A new repository version is automatically created each time content is
    added to or removed from a repository. Furthermore, it's possible to
    inspect any repository version and discover which content is present, which
    content was removed, and which content was added. This test case explores
    these features.

    This test targets the following issues:

    * `Pulp #3059 <https://pulp.plan.io/issues/3059>`_
    * `Pulp #3234 <https://pulp.plan.io/issues/3234>`_
    * `Pulp Smash #878 <https://github.com/PulpQE/pulp-smash/issues/878>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.page_handler)
        cls.remote = {}
        cls.repo = {}
        cls.content = {}

    @classmethod
    def tearDownClass(cls):
        """Destroy resources created by test methods."""
        if cls.remote:
            cls.client.delete(cls.remote['pulp_href'])
        if cls.repo:
            cls.client.delete(cls.repo['pulp_href'])

    def test_01_create_repository(self):
        """Create a repository.

        Assert that:

        * The ``versions_href`` API call is correct.
        * The ``latest_version_href`` API call is correct.
        """
        self.repo.update(self.client.post(FILE_REPO_PATH, gen_repo()))

        repo_versions = get_versions(self.repo)
        self.assertEqual(len(repo_versions), 1, repo_versions)

        self.assertEqual(self.repo['latest_version_href'], f"{self.repo['pulp_href']}versions/0/")

    @skip_if(bool, 'repo', False)
    def test_02_sync_content(self):
        """Sync content into the repository.

        Assert that:

        * The ``versions_href`` API call is correct.
        * The ``latest_version_href`` API call is correct.
        * The ``content_hrefs`` attribute is correct.
        * The ``content_added_hrefs`` attribute is correct.
        * The ``content_removed_hrefs`` attribute is correct.
        * The ``content_summary`` attribute is correct.
        * The ``content_added_summary`` attribute is correct.
        * The ``content_removed_summary`` attribute is correct.
        """
        body = gen_file_remote()
        self.remote.update(self.client.post(FILE_REMOTE_PATH, body))
        sync(self.cfg, self.remote, self.repo)
        repo = self.client.get(self.repo['pulp_href'])

        repo_versions = get_versions(repo)
        self.assertEqual(len(repo_versions), 2, repo_versions)

        self.assertIsNotNone(repo['latest_version_href'])

        content_hrefs = get_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(
            len(content_hrefs), FILE_FIXTURE_COUNT, content_hrefs
        )

        content = get_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(content), FILE_FIXTURE_COUNT)

        content_added = get_added_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(content_added), FILE_FIXTURE_COUNT)

        content_removed = get_removed_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(content_removed), 0)

        content_summary = get_content_summary(repo)
        self.assertDictEqual(content_summary, FILE_FIXTURE_SUMMARY)

        content_added_summary = get_added_content_summary(repo)
        self.assertDictEqual(content_added_summary, FILE_FIXTURE_SUMMARY)

        content_removed_summary = get_removed_content_summary(repo)
        self.assertDictEqual(content_removed_summary, {})

    @skip_if(bool, 'repo', False)
    def test_03_remove_content(self):
        """Remove content from the repository.

        Make roughly the same assertions as :meth:`test_02_sync_content`.
        """
        repo = self.client.get(self.repo['pulp_href'])
        self.content.update(choice(get_content(repo)[FILE_CONTENT_NAME]))

        modify_repo(self.cfg, self.repo, remove_units=[self.content])
        repo = self.client.get(self.repo['pulp_href'])

        repo_versions = get_versions(repo)
        self.assertEqual(len(repo_versions), 3, repo_versions)

        self.assertIsNotNone(repo['latest_version_href'])

        content_hrefs = get_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(
            len(content_hrefs), FILE_FIXTURE_COUNT - 1, content_hrefs
        )

        content = get_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(content), FILE_FIXTURE_COUNT - 1)

        added_content = get_added_content(repo)[FILE_CONTENT_NAME]
        self.assertListEqual(added_content, [], added_content)

        removed_content = get_removed_content(repo)[FILE_CONTENT_NAME]
        self.assertListEqual(removed_content, [self.content], removed_content)

        content_summary = get_content_summary(repo)
        self.assertDictEqual(
            content_summary, {FILE_CONTENT_NAME: FILE_FIXTURE_COUNT - 1}
        )

        content_added_summary = get_added_content_summary(repo)
        self.assertDictEqual(content_added_summary, {})

        content_removed_summary = get_removed_content_summary(repo)
        self.assertDictEqual(content_removed_summary, {FILE_CONTENT_NAME: 1})

    @skip_if(bool, 'repo', False)
    def test_04_add_content(self):
        """Add content to the repository.

        Make roughly the same assertions as :meth:`test_02_sync_content`.
        """
        repo = self.client.get(self.repo['pulp_href'])
        modify_repo(self.cfg, self.repo, add_units=[self.content])
        repo = self.client.get(self.repo['pulp_href'])

        repo_versions = get_versions(repo)
        self.assertEqual(len(repo_versions), 4, repo_versions)

        self.assertIsNotNone(repo['latest_version_href'])

        content_hrefs = get_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(
            len(content_hrefs), FILE_FIXTURE_COUNT, content_hrefs
        )

        content = get_content(repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(content), FILE_FIXTURE_COUNT)

        added_content = get_added_content(repo)[FILE_CONTENT_NAME]
        self.assertListEqual(added_content, [self.content], added_content)

        removed_content = get_removed_content(repo)[FILE_CONTENT_NAME]
        self.assertListEqual(removed_content, [], removed_content)

        content_summary = get_content_summary(repo)
        self.assertDictEqual(content_summary, FILE_FIXTURE_SUMMARY)

        content_added_summary = get_added_content_summary(repo)
        self.assertDictEqual(content_added_summary, {FILE_CONTENT_NAME: 1})

        content_removed_summary = get_removed_content_summary(repo)
        self.assertDictEqual(content_removed_summary, {})

    def get_content_summary(self, repo):
        """Get the ``content_summary`` for the given repository."""
        repo_versions = get_versions(repo)
        content_summaries = [
            repo_version['content_summary']
            for repo_version in repo_versions
            if repo_version['pulp_href'] == repo['latest_version_href']
        ]
        self.assertEqual(len(content_summaries), 1, content_summaries)
        return content_summaries[0]


class SyncChangeRepoVersionTestCase(unittest.TestCase):
    """Verify whether sync of repository updates repository version."""

    def test_all(self):
        """Verify whether the sync of a repository updates its version.

        This test explores the design choice stated in the `Pulp #3308`_ that a
        new repository version is created even if the sync does not add or
        remove any content units. Even without any changes to the remote if a
        new sync occurs, a new repository version is created.

        .. _Pulp #3308: https://pulp.plan.io/issues/3308

        Do the following:

        1. Create a repository, and a remote.
        2. Sync the repository.
        3. Remove all content - one by one.
        3. Verify that the repository version is equal to the number of operations.
        """
        cfg = config.get_config()
        client = api.Client(cfg, api.json_handler)

        repo = client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo['pulp_href'])

        body = gen_file_remote()
        remote = client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(client.delete, remote['pulp_href'])

        sync(cfg, remote, repo)
        repo = client.get(repo['pulp_href'])
        for file_content in get_content(repo)[FILE_CONTENT_NAME]:
            modify_repo(cfg, repo, remove_units=[file_content])
        repo = client.get(repo['pulp_href'])
        path = urlsplit(repo['latest_version_href']).path
        latest_repo_version = int(path.split('/')[-2])
        self.assertEqual(latest_repo_version, 4)


class AddRemoveRepoVersionTestCase(unittest.TestCase):
    """Create and delete repository versions.

    This test targets the following issues:

    * `Pulp #3219 <https://pulp.plan.io/issues/3219>`_
    * `Pulp Smash #871 <https://github.com/PulpQE/pulp-smash/issues/871>`_
    """

    # `cls.content[i]` is a dict.
    # pylint:disable=unsubscriptable-object

    @classmethod
    def setUpClass(cls):
        """Add content to Pulp."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        populate_pulp(cls.cfg, url=FILE_LARGE_FIXTURE_MANIFEST_URL)
        # We need at least three content units. Choosing a relatively low
        # number is useful, to limit how many repo versions are created, and
        # thus how long the test takes.
        cls.content = sample(cls.client.get(FILE_CONTENT_PATH)['results'], 10)

    def setUp(self):
        """Create a repository and give it nine new versions."""
        self.repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, self.repo['pulp_href'])

        # Don't upload the last content unit. The test case might upload it to
        # create a new repo version within the test.
        for content in self.content[:-1]:
            self.client.post(
                self.repo['pulp_href'] + "modify/",
                {'add_content_units': [content['pulp_href']]}
            )
        self.repo = self.client.get(self.repo['pulp_href'])
        self.repo_version_hrefs = tuple(
            version['pulp_href'] for version in get_versions(self.repo)
        )

    def test_delete_first_version(self):
        """Delete the first repository version."""
        delete_version(self.repo, self.repo_version_hrefs[0])
        with self.assertRaises(HTTPError):
            get_content(self.repo, self.repo_version_hrefs[0])
        for repo_version_href in self.repo_version_hrefs[1:]:
            artifact_paths = get_artifact_paths(self.repo, repo_version_href)
            self.assertIn(self.content[0]['artifact'], artifact_paths)

    def test_delete_last_version(self):
        """Delete the last repository version.

        Create a new repository version from the second-to-last repository
        version. Verify that the content unit from the old last repository
        version is not in the new last repository version.
        """
        # Delete the last repo version.
        delete_version(self.repo, self.repo_version_hrefs[-1])
        with self.assertRaises(HTTPError):
            get_content(self.repo, self.repo_version_hrefs[-1])

        # Make new repo version from new last repo version.
        self.client.post(
            self.repo['pulp_href'] + "modify/",
            {'add_content_units': [self.content[-1]['pulp_href']]}
        )
        self.repo = self.client.get(self.repo['pulp_href'])
        artifact_paths = get_artifact_paths(self.repo)

        self.assertNotIn(self.content[-2]['artifact'], artifact_paths)
        self.assertIn(self.content[-1]['artifact'], artifact_paths)

    def test_delete_middle_version(self):
        """Delete a middle version."""
        index = randint(1, len(self.repo_version_hrefs) - 2)
        delete_version(self.repo, self.repo_version_hrefs[index])

        with self.assertRaises(HTTPError):
            get_content(self.repo, self.repo_version_hrefs[index])

        for repo_version_href in self.repo_version_hrefs[index + 1:]:
            artifact_paths = get_artifact_paths(self.repo, repo_version_href)
            self.assertIn(self.content[index]['artifact'], artifact_paths)

    def test_delete_publication(self):
        """Delete a publication.

        Delete a repository version, and verify the associated publication is
        also deleted.
        """
        publication = create_file_publication(self.cfg, self.repo)
        delete_version(self.repo)

        with self.assertRaises(HTTPError):
            self.client.get(publication['pulp_href'])


class ContentImmutableRepoVersionTestCase(unittest.TestCase):
    """Test whether the content present in a repo version is immutable.

    This test targets the following issue:

    * `Pulp Smash #953 <https://github.com/PulpQE/pulp-smash/issues/953>`_
    """

    def test_all(self):
        """Test whether the content present in a repo version is immutable.

        Do the following:

        1. Create a repository that has at least one repository version.
        2. Attempt to update the content of a repository version.
        3. Assert that an HTTP exception is raised.
        4. Assert that the repository version was not updated.
        """
        cfg = config.get_config()
        client = api.Client(cfg, api.json_handler)

        repo = client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo['pulp_href'])

        body = gen_file_remote()
        remote = client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(client.delete, remote['pulp_href'])

        sync(cfg, remote, repo)

        latest_version_href = client.get(repo['pulp_href'])['latest_version_href']
        with self.assertRaises(HTTPError):
            client.post(latest_version_href)
        repo = client.get(repo['pulp_href'])
        self.assertEqual(latest_version_href, repo['latest_version_href'])


class FilterRepoVersionTestCase(unittest.TestCase):
    """Test whether repository versions can be filtered.

    These tests target the following issues:

    * `Pulp #3238 <https://pulp.plan.io/issues/3238>`_
    * `Pulp #3536 <https://pulp.plan.io/issues/3536>`_
    * `Pulp #3557 <https://pulp.plan.io/issues/3557>`_
    * `Pulp #3558 <https://pulp.plan.io/issues/3558>`_
    * `Pulp Smash #880 <https://github.com/PulpQE/pulp-smash/issues/880>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables.

        Add content to Pulp.
        """
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)

        populate_pulp(cls.cfg)
        cls.contents = cls.client.get(FILE_CONTENT_PATH)['results']

    def setUp(self):
        """Create a repository and give it new versions."""
        self.repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, self.repo['pulp_href'])

        for content in self.contents[:10]:  # slice is arbitrary upper bound
            modify_repo(self.cfg, self.repo, add_units=[content])
            sleep(1)
        self.repo = self.client.get(self.repo['pulp_href'])

    def test_filter_invalid_content(self):
        """Filter repository version by invalid content."""
        with self.assertRaises(HTTPError):
            get_versions(self.repo, {'content': utils.uuid4()})

    def test_filter_valid_content(self):
        """Filter repository versions by valid content."""
        content = choice(self.contents)
        repo_versions = get_versions(self.repo, {'content': content['pulp_href']})
        for repo_version in repo_versions:
            self.assertIn(
                self.client.get(content['pulp_href']),
                get_content(self.repo, repo_version['pulp_href'])[
                    FILE_CONTENT_NAME]
            )

    def test_filter_invalid_date(self):
        """Filter repository version by invalid date."""
        criteria = utils.uuid4()
        for params in (
                {'pulp_created': criteria},
                {'pulp_created__gt': criteria, 'pulp_created__lt': criteria},
                {'pulp_created__gte': criteria, 'pulp_created__lte': criteria},
                {'pulp_created__range': ','.join((criteria, criteria))}):
            with self.subTest(params=params):
                with self.assertRaises(HTTPError):
                    get_versions(self.repo, params)

    def test_filter_valid_date(self):
        """Filter repository version by a valid date."""
        dates = self.get_repo_versions_attr('pulp_created')
        for params, num_results in (
                ({'pulp_created': dates[0]},
                 1),
                ({'pulp_created__gt': dates[0], 'pulp_created__lt': dates[-1]},
                 len(dates) - 2),
                ({'pulp_created__gte': dates[0], 'pulp_created__lte': dates[-1]},
                 len(dates)),
                ({'pulp_created__range': ','.join((dates[0], dates[1]))},
                 2)):
            with self.subTest(params=params):
                results = get_versions(self.repo, params)
                self.assertEqual(len(results), num_results, results)

    def test_filter_nonexistent_version(self):
        """Filter repository version by a nonexistent version number."""
        criteria = -1
        for params in (
                {'number': criteria},
                {'number__gt': criteria, 'number__lt': criteria},
                {'number__gte': criteria, 'number__lte': criteria},
                {'number__range': ','.join((str(criteria), str(criteria)))}):
            with self.subTest(params=params):
                versions = get_versions(self.repo, params)
                self.assertEqual(len(versions), 0, versions)

    def test_filter_invalid_version(self):
        """Filter repository version by an invalid version number."""
        criteria = utils.uuid4()
        for params in (
                {'number': criteria},
                {'number__gt': criteria, 'number__lt': criteria},
                {'number__gte': criteria, 'number__lte': criteria},
                {'number__range': ','.join((criteria, criteria))}):
            with self.subTest(params=params):
                with self.assertRaises(HTTPError):
                    get_versions(self.repo, params)

    def test_filter_valid_version(self):
        """Filter repository version by a valid version number."""
        numbers = self.get_repo_versions_attr('number')
        for params, num_results in (
                ({'number': numbers[0]},
                 1),
                ({'number__gt': numbers[0], 'number__lt': numbers[-1]},
                 len(numbers) - 2),
                ({'number__gte': numbers[0], 'number__lte': numbers[-1]},
                 len(numbers)),
                ({'number__range': '{},{}'.format(numbers[0], numbers[1])},
                 2)):
            with self.subTest(params=params):
                results = get_versions(self.repo, params)
                self.assertEqual(len(results), num_results, results)

    def test_deleted_version_filter(self):
        """Delete a repository version and filter by its number."""
        numbers = self.get_repo_versions_attr('number')
        delete_version(self.repo)
        versions = get_versions(self.repo, {'number': numbers[-1]})
        self.assertEqual(len(versions), 0, versions)

    def get_repo_versions_attr(self, attr):
        """Get an ``attr`` about each version of ``self.repo``.

        Return as sorted list.
        """
        attributes = [version[attr] for version in get_versions(self.repo)]
        attributes.sort()
        return attributes


class CreatedResourcesTaskTestCase(unittest.TestCase):
    """Verify whether task report shows that a repository version was created.

    This test targets the following issue:

    `Pulp Smash #876 <https://github.com/PulpQE/pulp-smash/issues/876>`_.
    """

    def test_all(self):
        """Verify whether task report shows repository version was created."""
        cfg = config.get_config()
        client = api.Client(cfg, api.json_handler)

        repo = client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo['pulp_href'])

        body = gen_file_remote()
        remote = client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(client.delete, remote['pulp_href'])

        call_report = sync(cfg, remote, repo)
        for key in ('repositories', 'versions'):
            self.assertIn(
                key,
                call_report['pulp_href'],
                call_report
            )


class CreateRepoBaseVersionTestCase(unittest.TestCase):
    """Test whether one can create a repository version from any version.

    This test targets the following issues:

    `Pulp #3360 <https://pulp.plan.io/issues/3360>`_
    `Pulp #4035 <https://pulp.plan.io/issues/4035>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        delete_orphans(cls.cfg)
        populate_pulp(cls.cfg, url=FILE_LARGE_FIXTURE_MANIFEST_URL)
        cls.client = api.Client(cls.cfg, api.page_handler)
        cls.content = cls.client.get(FILE_CONTENT_PATH)

    def test_same_repository(self):
        """Test ``base_version`` for the same repository.

        Do the following:

        1. Create a repository.
        2. Sync the repository (this creates repository version 1).
        3. Add a new content unit a new repository version (this create
           repository version 2).
        4. Create a new repository version using version 1 as ``base_version``
           (this creates version 3).
        5. Check that version 1 and version 3 have the same content.
        """
        # create repo version 1
        repo = self.create_sync_repo()
        version_content = []
        version_content.append(
            sorted(
                [
                    remove_created_key(item)
                    for item in get_content(repo)[FILE_CONTENT_NAME]
                ],
                key=lambda item: item['pulp_href'],
            )
        )
        self.assertIsNone(get_versions(repo)[1]['base_version'])

        content = self.content.pop()

        # create repo version 2
        modify_repo(self.cfg, repo, add_units=[content])
        repo = self.client.get(repo['pulp_href'])

        # create repo version 3 from version 1
        base_version = get_versions(repo)[1]['pulp_href']
        modify_repo(self.cfg, repo, base_version=base_version)
        repo = self.client.get(repo['pulp_href'])

        # assert that base_version of the version 3 points to version 1
        self.assertEqual(get_versions(repo)[3]['base_version'], base_version)

        # assert that content on version 1 is equal to content on version 3
        version_content.append(
            sorted(
                [
                    remove_created_key(item)
                    for item in get_content(repo)[FILE_CONTENT_NAME]
                ],
                key=lambda item: item['pulp_href'],
            )
        )
        self.assertEqual(
            version_content[0],
            version_content[1],
            version_content
        )

    def test_different_repository(self):
        """Test ``base_version`` for different repositories.

        Do the following:

        1. Create a new repository A and sync it.
        2. Create a new repository B and a new version for this repository
           specify repository A version 1 as the ``base_version``.
        3. Check that repository A version 1 and repository B version 1 have
           the same content.
        """
        # create repo A
        repo = self.create_sync_repo()
        version_content = []
        version_content.append(
            sorted(
                [
                    remove_created_key(item)
                    for item in get_content(repo)[FILE_CONTENT_NAME]
                ],
                key=lambda item: item['pulp_href'],
            )
        )
        self.assertIsNone(get_versions(repo)[1]['base_version'])

        # get repo A version 1 to be used as base_version
        base_version = get_versions(repo)[1]['pulp_href']

        # create repo B
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])

        # create a version for repo B using repo A version 1 as base_version
        modify_repo(self.cfg, repo, base_version=base_version)
        repo = self.client.get(repo['pulp_href'])

        # assert that base_version of repo B points to version 1 of repo A
        self.assertEqual(get_versions(repo)[1]['base_version'], base_version)

        # assert that content on version 1 of repo A is equal to content on
        # version 1 repo B
        version_content.append(
            sorted(
                [
                    remove_created_key(item)
                    for item in get_content(repo)[FILE_CONTENT_NAME]
                ],
                key=lambda item: item['pulp_href'],
            )
        )

        self.assertEqual(
            version_content[0],
            version_content[1],
            version_content
        )

    def test_base_version_other_parameters(self):
        """Test ``base_version`` can be used together with other parameters.

        ``add_content_units`` and ``remove_content_units``.
        """
        # create repo version 1
        repo = self.create_sync_repo()
        version_1_content = [
            remove_created_key(item)
            for item in get_content(repo)[FILE_CONTENT_NAME]
        ]
        self.assertIsNone(get_versions(repo)[1]['base_version'])

        # create repo version 2 from version 1
        base_version = get_versions(repo)[1]['pulp_href']
        added_content = remove_created_key(self.content.pop())
        removed_content = choice(version_1_content)
        modify_repo(
            self.cfg, repo,
            base_version=base_version,
            add_units=[added_content],
            remove_units=[removed_content]
        )
        repo = self.client.get(repo['pulp_href'])
        version_2_content = [
            remove_created_key(item)
            for item in get_content(repo)[FILE_CONTENT_NAME]
        ]

        # assert that base_version of the version 2 points to version 1
        self.assertEqual(get_versions(repo)[2]['base_version'], base_version)

        # assert that the removed content is not present on repo version 2
        self.assertNotIn(removed_content, version_2_content)

        # assert that the added content is present on repo version 2
        self.assertIn(added_content, version_2_content)

        # assert that the same amount of units are present in both versions
        self.assertEqual(len(version_1_content), len(version_2_content))

    def test_base_version_exception(self):
        """Exception is raised when non-existent ``base_version`` is used.

        Do the following:

        1. Create a repository B and an attempt to specify a non-existent
           ``base_version``.
        3. Assert that an HTTP exception is raised.
        """
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])

        with self.assertRaises(HTTPError):
            modify_repo(self.cfg, repo, base_version=utils.uuid4())

    def create_sync_repo(self):
        """Create, and sync a repo."""
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])

        body = gen_file_remote(url=FILE_FIXTURE_MANIFEST_URL)
        remote = self.client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(self.client.delete, remote['pulp_href'])

        sync(self.cfg, remote, repo)
        return self.client.get(repo['pulp_href'])


class UpdateRepoVersionTestCase(unittest.TestCase):
    """Repository version can not be updated using PATCH or PUT.

    Assert that an HTTP exception is raised.

    This test targets the following issue:

    * `Pulp #4667 <https://pulp.plan.io/issues/4667>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)

    def test_http_error(self):
        """Test partial update repository version."""
        remote = self.client.post(FILE_REMOTE_PATH, gen_file_remote())
        self.addCleanup(self.client.delete, remote['pulp_href'])

        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])

        # create repo version
        sync(self.cfg, remote, repo)
        repo = self.client.get(repo['pulp_href'])

        self.assert_patch(repo)
        self.assert_put(repo)

    def assert_patch(self, repo):
        """Assert PATCH method raises an HTTP exception."""
        previous_repo_name = repo['name']
        with self.assertRaises(HTTPError):
            self.client.patch(
                repo['latest_version_href'],
                {'name': utils.uuid4()}
            )
        repo = self.client.get(repo['pulp_href'])
        self.assertEqual(previous_repo_name, repo['name'], repo)

    def assert_put(self, repo):
        """Assert PUT method raises an HTTP exception."""
        previous_repo_name = repo['name']
        with self.assertRaises(HTTPError):
            repo['name'] = utils.uuid4()
            self.client.put(repo['latest_version_href'], repo)
        repo = self.client.get(repo['pulp_href'])
        self.assertEqual(previous_repo_name, repo['name'], repo)


class FilterArtifactsTestCase(unittest.TestCase):
    """Filter artifacts by repository version.

    This test targets the following issue:

    * `Pulp #4811 <https://pulp.plan.io/issues/4811>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables.

        Populate Pulp with artifacts to show how the filter is related to
        repository version.
        """
        cls.cfg = config.get_config()
        populate_pulp(cls.cfg, url=FILE_MANY_FIXTURE_MANIFEST_URL)
        cls.client = api.Client(cls.cfg)

    def test_filter_last_repository_version(self):
        """Filter by last repository version.

        For a repository with more than one version.
        """
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])

        for url in [FILE2_FIXTURE_MANIFEST_URL, FILE_FIXTURE_MANIFEST_URL]:
            remote = self.client.post(
                FILE_REMOTE_PATH,
                gen_file_remote(url=url)
            )
            self.addCleanup(self.client.delete, remote['pulp_href'])
            sync(self.cfg, remote, repo)
            repo = self.client.get(repo['pulp_href'])

        artifacts = self.client.get(
            ARTIFACTS_PATH,
            params={'repository_version': repo['latest_version_href']}
        )
        # Even though every sync adds 3 content units to the repository the fixture data contains
        # the same relative urls so the second sync replaces the first 3, leaving a total of 3 each
        # time
        self.assertEqual(len(artifacts), FILE_FIXTURE_COUNT, artifacts)

    def test_filter_invalid_repo_version(self):
        """Filter by invalid repository version."""
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])
        with self.assertRaises(HTTPError) as ctx:
            self.client.using_handler(api.json_handler).get(
                ARTIFACTS_PATH,
                params={'repository_version': repo['pulp_href']}
            )
        for key in ('uri', 'repositoryversion', 'not', 'found'):
            self.assertIn(
                key,
                ctx.exception.response.json()[0].lower(),
                ctx.exception.response
            )

    def test_filter_valid_repo_version(self):
        """Filter by valid repository version."""
        remote = self.client.post(FILE_REMOTE_PATH, gen_file_remote())
        self.addCleanup(self.client.delete, remote['pulp_href'])
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])
        sync(self.cfg, remote, repo)
        repo = self.client.get(repo['pulp_href'])
        artifacts = self.client.get(
            ARTIFACTS_PATH,
            params={'repository_version': repo['latest_version_href']}
        )
        self.assertEqual(len(artifacts), FILE_FIXTURE_COUNT, artifacts)


class DeleteRepoVersionResourcesTestCase(unittest.TestCase):
    """Test whether removing a repository version affects related resources.

    Test whether removing a repository version will remove a related Publication.
    Test whether removing a repository version a Distribution will not be removed.

    This test targets the following issue:

    `Pulp #5303 <https://pulp.plan.io/issues/5303>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)

    def test_delete_publication(self):
        """Publication is removed once the repository version is removed."""
        repo = self.create_sync_repo(2)
        version_href = choice(self.client.get(repo['versions_href']))['pulp_href']
        publication = create_file_publication(self.cfg, repo, version_href)

        # delete repo version used to create publication
        self.client.delete(version_href)

        with self.assertRaises(HTTPError) as ctx:
            self.client.get(publication['pulp_href'])

        for key in ('not', 'found'):
            self.assertIn(
                key,
                ctx.exception.response.json()['detail'].lower(),
                ctx.exception.response,
            )

    def test_delete_distribution(self):
        """Distribution is not removed once repository version is removed."""
        repo = self.create_sync_repo(2)
        version_href = choice(self.client.get(repo['versions_href']))['pulp_href']
        publication = create_file_publication(self.cfg, repo, version_href)

        distribution = self.client.post(
            FILE_DISTRIBUTION_PATH, gen_distribution(publication=publication['pulp_href'])
        )
        self.addCleanup(self.client.delete, distribution['pulp_href'])

        # delete repo version used to create publication
        self.client.delete(version_href)

        updated_distribution = self.client.get(distribution['pulp_href'])
        self.assertIsNone(updated_distribution['publication'], updated_distribution)

    def create_sync_repo(self, number_syncs=1):
        """Create and sync a repository.

        Given the number of times to be synced.
        """
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['pulp_href'])

        remote = self.client.post(FILE_REMOTE_PATH, gen_file_remote())
        self.addCleanup(self.client.delete, remote['pulp_href'])

        for _ in range(number_syncs):
            sync(self.cfg, remote, repo)
        return self.client.get(repo['pulp_href'])


class ClearAllUnitsRepoVersionTestCase(unittest.TestCase):
    """Test clear of all units of a given repository version.

    This test targets the following issue:

    `Pulp #4956 <https://pulp.plan.io/issues/4956>`_
    """

    @classmethod
    def setUpClass(cls):
        """Add content to Pulp."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)
        # Populate Pulp to create content units.
        populate_pulp(cls.cfg, url=FILE_LARGE_FIXTURE_MANIFEST_URL)
        cls.content = sample(cls.client.get(FILE_CONTENT_PATH), 10)

    def setUp(self):
        """Create and sync a repository."""
        self.repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, self.repo['pulp_href'])
        remote = self.client.post(FILE_REMOTE_PATH, gen_file_remote())
        self.addCleanup(self.client.delete, remote['pulp_href'])
        sync(self.cfg, remote, self.repo)
        self.repo = self.client.get(self.repo['pulp_href'])

    def test_add_and_clear_all_units(self):
        """Test addition and removal of all units for a given repository version."""
        content = choice(self.content)
        modify_repo(
            self.cfg, self.repo,
            add_units=[content],
            remove_units=['*']
        )
        self.repo = self.client.get(self.repo['pulp_href'])

        added_content = get_content(self.repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(added_content), 1, added_content)

        self.assertEqual(
            remove_created_key(content), remove_created_key(added_content[0])
        )

    def test_clear_all_units_using_base_version(self):
        """Test clear all units using base version."""
        for content in self.content:
            modify_repo(self.cfg, self.repo, add_units=[content])

        self.repo = self.client.get(self.repo['pulp_href'])
        base_version = get_versions(self.repo)[0]['pulp_href']

        modify_repo(
            self.cfg, self.repo,
            base_version=base_version, remove_units=['*']
        )
        self.repo = self.client.get(self.repo['pulp_href'])

        content_last_version = get_content(self.repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(content_last_version), 0, content_last_version)

    def test_clear_all_units(self):
        """Test clear all units of a given repository version."""
        added_content = sorted(
            [content['pulp_href'] for content in get_content(self.repo)[FILE_CONTENT_NAME]]
        )

        modify_repo(self.cfg, self.repo, remove_units=['*'])
        self.repo = self.client.get(self.repo['pulp_href'])
        removed_content = sorted(
            [
                content['pulp_href']
                for content in get_removed_content(self.repo)[FILE_CONTENT_NAME]
            ]
        )
        self.assertEqual(added_content, removed_content)
        content = get_content(self.repo)[FILE_CONTENT_NAME]
        self.assertEqual(len(content), 0, content)

    def test_http_error(self):
        """Test http error is raised."""
        added_content = choice(get_added_content(self.repo)[FILE_CONTENT_NAME])
        with self.assertRaises(HTTPError) as ctx:
            self.client.post(
                self.repo['pulp_href'] + "modify/",
                {'remove_content_units': ['*', added_content['pulp_href']]},
            )
        for key in ('content', 'units', '*'):
            self.assertIn(
                key,
                ctx.exception.response.json()['remove_content_units'][0].lower(),
                ctx.exception.response,
            )
