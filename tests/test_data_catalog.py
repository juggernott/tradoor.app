import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from alphaloop.web.api import create_app
from alphaloop.web.catalog import HistoricalCatalog


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    content = 'date,symbol,close\n'+'\n'.join(f'2026-01-{d:02d},{s},100' for d in range(1,11) for s in ['BTC','ETH'])
    (tmp_path/'prices.csv').write_bytes(content.encode())
    entry = {'id':'archive','label':'Daily prices','kind':'daily-prices','file':'prices.csv',
             'sha256':hashlib.sha256(content.encode()).hexdigest(),'workspaces':['alice'],
             'customer_use_approved':True,'rights_reference':'test-only grant','attribution':'Required credit'}
    path=tmp_path/'catalog.json'
    def save():
        path.write_text(json.dumps({'datasets':[entry]}))
    save()
    monkeypatch.setenv('TRADOOR_DATA_CATALOG',str(path))
    return entry,save,tmp_path


def test_grants_hide_private_metadata_and_deny_unapproved_content(catalog):
    entry,save,_=catalog
    assert HistoricalCatalog('bob').list()==[]
    with pytest.raises(KeyError):
        HistoricalCatalog('bob').read('archive')
    visible=HistoricalCatalog('alice').list()[0]
    assert 'file' not in visible and 'rights_reference' not in visible
    assert visible['attribution']=='Required credit'
    entry['customer_use_approved']=False;save()
    assert HistoricalCatalog('alice').list()==[]


def test_checksum_and_path_escape_fail_closed(catalog):
    entry,save,root=catalog
    (root/'prices.csv').write_text('changed')
    with pytest.raises(ValueError,match='checksum'):
        HistoricalCatalog('alice').read('archive')
    outside=root.parent/'outside.csv';outside.write_text('private')
    entry['file']='../outside.csv';save()
    with pytest.raises(ValueError,match='inside'):
        HistoricalCatalog('alice').read('archive')


def test_import_copies_only_granted_data_to_private_workspace(catalog,monkeypatch):
    _,_,root=catalog
    monkeypatch.setenv('TRADOOR_WORKSPACE_ID','alice')
    with TestClient(create_app(root/'alice.db',local=True,allowed_hosts=['testserver'])) as client:
        response=client.post('/api/catalog/archive/import',json={})
        assert response.status_code==201,response.text
        imported=client.get('/api/datasets/'+response.json()['id']).json()
        assert imported['attribution']=='Required credit'
        assert imported['catalog_id']=='archive'
    monkeypatch.setenv('TRADOOR_WORKSPACE_ID','bob')
    with TestClient(create_app(root/'bob.db',local=True,allowed_hosts=['testserver'])) as client:
        assert client.get('/api/catalog').json()['datasets']==[]
        assert client.post('/api/catalog/archive/import',json={}).status_code==404
