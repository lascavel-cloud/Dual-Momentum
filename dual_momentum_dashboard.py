KeyError: This app has encountered an error. The original error message is redacted to prevent data leaks. Full error details have been recorded in the logs (if you're on Streamlit Cloud, click on 'Manage app' in the lower right of your app).
Traceback:
File "/mount/src/dual-momentum/dual_momentum_dashboard.py", line 33, in <module>
    data_dict = fetch_data()
File "/home/adminuser/venv/lib/python3.14/site-packages/streamlit/runtime/caching/cache_utils.py", line 281, in __call__
    return self._get_or_create_cached_value(args, kwargs, spinner_message)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.14/site-packages/streamlit/runtime/caching/cache_utils.py", line 326, in _get_or_create_cached_value
    return self._handle_cache_miss(cache, value_key, func_args, func_kwargs)
           ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.14/site-packages/streamlit/runtime/caching/cache_utils.py", line 385, in _handle_cache_miss
    computed_value = self._info.func(*func_args, **func_kwargs)
File "/mount/src/dual-momentum/dual_momentum_dashboard.py", line 25, in fetch_data
    df = yf.download(t, start=start, end=end, progress=False)['Adj Close']
         ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.14/site-packages/pandas/core/frame.py", line 4377, in __getitem__
    return self._getitem_multilevel(key)
           ~~~~~~~~~~~~~~~~~~~~~~~~^^^^^
File "/home/adminuser/venv/lib/python3.14/site-packages/pandas/core/frame.py", line 4435, in _getitem_multilevel
    loc = self.columns.get_loc(key)
File "/home/adminuser/venv/lib/python3.14/site-packages/pandas/core/indexes/multi.py", line 3523, in get_loc
    loc = self._get_level_indexer(key, level=0)
File "/home/adminuser/venv/lib/python3.14/site-packages/pandas/core/indexes/multi.py", line 3885, in _get_level_indexer
    idx = self._get_loc_single_level_index(level_index, key)
File "/home/adminuser/venv/lib/python3.14/site-packages/pandas/core/indexes/multi.py", line 3458, in _get_loc_single_level_index
    return level_index.get_loc(key)
           ~~~~~~~~~~~~~~~~~~~^^^^^
File "/home/adminuser/venv/lib/python3.14/site-packages/pandas/core/indexes/base.py", line 3648, in get_loc
    raise KeyError(key) from err
