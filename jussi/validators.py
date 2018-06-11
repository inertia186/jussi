# -*- coding: utf-8 -*-
import itertools as it

import structlog
from funcy.decorators import Call
from funcy.decorators import decorator

from .errors import InvalidRequest
from .errors import JussiCustomJsonOpLengthError
from .errors import JussiLimitsError
from .errors import ServerError
from .errors import UpstreamResponseError
from .typedefs import JsonRpcRequest
from .typedefs import JsonRpcResponse
from .typedefs import SingleJsonRpcRequest
from .typedefs import SingleJsonRpcResponse

logger = structlog.get_logger(__name__)

GET_BLOCK_RESULT_KEYS = {"previous",
                         "timestamp",
                         "witness",
                         "transaction_merkle_root",
                         "extensions",
                         "witness_signature",
                         "transactions",
                         "block_id",
                         "signing_key",
                         "transaction_ids"}

JSONRPC_REQUEST_KEYS = {'id', 'jsonrpc', 'method', 'params'}

CUSTOM_JSON_SIZE_LIMIT = 2000
CUSTOM_JSON_FOLLOW_RATE = 2

BROADCAST_TRANSACTION_METHODS = {
    'broadcast_transaction',
    'broadcast_transaction_synchronous'
}


@decorator
async def validate_response_decorator(call: Call) -> SingleJsonRpcResponse:
    """Return response if valid
    """
    json_response = await call()
    try:
        if is_get_block_request(call.jsonrpc_request):
            assert is_valid_get_block_response(
                call.jsonrpc_request, json_response)
        return json_response
    except AssertionError as e:
        raise ServerError(sanic_request=call.sanic_http_request,
                          data={
                              'message': 'Bad or missing upstream response',
                              'upstream_response': json_response
                          },
                          exception=e)


#
# validate_* methods raise on invalid input
#


def validate_jsonrpc_request(jsonrpc_request: JsonRpcRequest) -> None:
    if isinstance(jsonrpc_request, dict):
        assert JSONRPC_REQUEST_KEYS.issuperset(jsonrpc_request.keys())
        assert len(jsonrpc_request.keys()) >= 2
        assert jsonrpc_request.get('jsonrpc') == '2.0', 'bad jsonrpc version'
        assert isinstance(jsonrpc_request.get('method'), str), ''
        assert isinstance(jsonrpc_request.get('id'),
                          (int, str, float, type(None))), 'bad jsonrpc id'
        assert isinstance(jsonrpc_request.get('params'),
                          (list, dict, type(None))), 'bad jsonrpc params'
    elif isinstance(jsonrpc_request, list):
        # pylint: disable=expression-not-assigned
        [validate_jsonrpc_request(r) for r in jsonrpc_request]
        # pylint: enable=expression-not-assigned
    elif isinstance(jsonrpc_request, SingleJsonRpcRequest):
        pass  # already be validated
    else:
        raise InvalidRequest(request=jsonrpc_request)


def validate_jussi_response(jsonrpc_request: JsonRpcRequest,
                            jsonrpc_response: JsonRpcResponse) -> None:
    if isinstance(jsonrpc_request, list):
        assert isinstance(jsonrpc_response, list)
        assert len(jsonrpc_request) > 0 and (jsonrpc_request) == len(
            jsonrpc_response)
        assert all(validate_jussi_response(req, resp) for req, resp in
                   zip(jsonrpc_request, jsonrpc_response))
    elif isinstance(jsonrpc_request, SingleJsonRpcRequest):
        assert is_valid_non_error_single_jsonrpc_response(jsonrpc_response)
        if is_get_block_request(jsonrpc_request):
            assert is_valid_get_block_response(
                jsonrpc_request, jsonrpc_response)
    else:
        raise UpstreamResponseError(data=jsonrpc_request.log_extra())


#
# is_valid_* methods return True or False, but they don't raise
#


def is_valid_jsonrpc_request(
        jsonrpc_request: JsonRpcRequest = None) -> bool:
    try:
        validate_jsonrpc_request(jsonrpc_request)
        return True
    except Exception as e:
        logger.error(f'{e}')
    return False


def is_valid_single_jsonrpc_response(
        jsonrpc_response: SingleJsonRpcResponse) -> bool:
    return isinstance(
        jsonrpc_response, dict) and len(
        jsonrpc_response.keys()) >= 2 and {
        'id', 'jsonrpc', 'result', 'error'}.issuperset(
        jsonrpc_response.keys())


def is_valid_non_error_single_jsonrpc_response(
        jsonrpc_response: SingleJsonRpcResponse) -> bool:
    return isinstance(
        jsonrpc_response, dict) and len(
        jsonrpc_response.keys()) >= 2 and {
        'id', 'jsonrpc', 'result'}.issuperset(
        jsonrpc_response.keys())


def is_valid_jsonrpc_response(jsonrpc_request: JsonRpcRequest,
                              jsonrpc_response: JsonRpcResponse) -> bool:
    if not is_valid_jsonrpc_request(jsonrpc_request):
        return False
    if isinstance(jsonrpc_request, SingleJsonRpcRequest):
        return isinstance(
            jsonrpc_response, dict) and is_valid_single_jsonrpc_response(
            jsonrpc_response)
    if isinstance(jsonrpc_response, list):
        return len(jsonrpc_request) > 0 and len(jsonrpc_request) == len(
            jsonrpc_response) and all(is_valid_single_jsonrpc_response(r)
                                      for r in jsonrpc_response)
    else:
        return False


def is_valid_non_error_jsonrpc_response(jsonrpc_request: JsonRpcRequest,
                                        jsonrpc_response: JsonRpcResponse) -> bool:
    if not is_valid_jsonrpc_request(jsonrpc_request):
        return False
    if isinstance(jsonrpc_request, SingleJsonRpcRequest):
        return isinstance(jsonrpc_response,
                          dict) and is_valid_non_error_single_jsonrpc_response(
            jsonrpc_response)
    if isinstance(jsonrpc_response, list):
        return len(jsonrpc_request) > 0 and len(jsonrpc_request) == len(
            jsonrpc_response) and all(
            is_valid_non_error_single_jsonrpc_response(r)
            for r in jsonrpc_response)
    else:
        return False


def is_valid_jussi_response(
        jsonrpc_request: SingleJsonRpcRequest,
        response: SingleJsonRpcResponse) -> bool:
    try:
        if not is_valid_jsonrpc_request(jsonrpc_request):
            return False
        if isinstance(jsonrpc_request, SingleJsonRpcRequest):
            if not is_valid_jsonrpc_response(
                    jsonrpc_request, response):
                return False
            if is_get_block_request(jsonrpc_request):
                return is_valid_get_block_response(jsonrpc_request, response)
            return True
        if isinstance(jsonrpc_request, list):
            return len(jsonrpc_request) > 0 and len(jsonrpc_request) == len(
                response) and all(
                is_valid_jussi_response(req, resp) for req,
                resp in
                zip(jsonrpc_request, response))
        return False
    except Exception as e:
        logger.error('is_valid_jussi_response error', e=e,
                     **jsonrpc_request.log_extra())
    return False


def is_valid_non_error_jussi_response(
        jsonrpc_request: SingleJsonRpcRequest,
        response: SingleJsonRpcResponse) -> bool:
    try:
        if not is_valid_jsonrpc_request(jsonrpc_request):
            return False
        if isinstance(jsonrpc_request, SingleJsonRpcRequest):
            if not is_valid_non_error_jsonrpc_response(
                    jsonrpc_request, response):
                return False
            if is_get_block_request(jsonrpc_request):
                return is_valid_get_block_response(jsonrpc_request, response)
            return True
        if isinstance(jsonrpc_request, list):
            return len(jsonrpc_request) > 0 and len(jsonrpc_request) == len(
                response) and all(
                is_valid_jussi_response(req, resp) for req,
                resp in
                zip(jsonrpc_request, response))
        return False
    except Exception as e:
        logger.error('is_valid_non_error_jussi_response error', e=e,
                     **jsonrpc_request.log_extra())
    return False


def is_get_block_request(jsonrpc_request: SingleJsonRpcRequest = None) -> bool:
    try:
        return jsonrpc_request.urn.namespace in (
            'steemd', 'appbase') and jsonrpc_request.urn.method == 'get_block'
    except Exception as e:
        logger.warning('is_get_block_request error', e=e,
                       **jsonrpc_request.log_extra())
        return False


def is_get_block_header_request(
        jsonrpc_request: SingleJsonRpcRequest = None) -> bool:
    try:
        return jsonrpc_request.urn.namespace in (
            'steemd', 'appbase') and jsonrpc_request.urn.method == 'get_block_header'
    except Exception as e:

        logger.warning('is_get_block_request error', e=e,
                       **jsonrpc_request.log_extra())
        return False


def is_get_dynamic_global_properties_request(
        jsonrpc_request: SingleJsonRpcRequest = None) -> bool:
    try:
        return jsonrpc_request.urn.namespace in (
            'steemd', 'appbase') and jsonrpc_request.urn.method == 'get_dynamic_global_properties'
    except Exception as e:
        logger.warning('is_get_dynamic_global_properties_request failed', e=e,
                       **jsonrpc_request.log_extra())
        return False


def is_valid_get_block_response(
        jsonrpc_request: SingleJsonRpcRequest,
        response: SingleJsonRpcResponse) -> bool:
    if not is_get_block_request(
            jsonrpc_request) and is_valid_non_error_single_jsonrpc_response(
            response):
        return False
    request_block_num, response_block_num = 'nope', 'nope'
    try:
        params = jsonrpc_request.urn.params
        if isinstance(params, list):
            request_block_num = params[0]
        elif isinstance(params, dict):
            request_block_num = params['block_num']
        else:
            raise ValueError(f'bad urn params from {jsonrpc_request}: {params} ')

        if 'result' not in response:
            raise Exception('jsonrpc response did not contain result')
        elif response['result'] is None:
            return False  # block does not exist yet

        if 'block_id' in response['result']:
            block_id = response['result']['block_id']
        elif 'block' in response['result']:
            block_id = response['result']['block']['block_id']
        else:
            return False
        response_block_num = block_num_from_id(block_id)
        assert int(request_block_num) == response_block_num
        return True
    except KeyError as e:
        logger.error('is_valid_get_block_response key error',
                     e=e,
                     response=response,
                     **jsonrpc_request.log_extra())
    except AssertionError:
        logger.error('request_block != response block_num',
                     request_block_num=request_block_num,
                     response_block_num=response_block_num)
    except Exception as e:
        logger.error('is_valid_get_block_response error', e=e,
                     **jsonrpc_request.log_extra())
    return False


def is_broadcast_transaction_request(jsonrpc_request: SingleJsonRpcRequest) -> bool:
    return jsonrpc_request.urn.method in BROADCAST_TRANSACTION_METHODS


def limit_broadcast_transaction_request(
        jsonrpc_request: SingleJsonRpcRequest, limits=None):

    if is_broadcast_transaction_request(jsonrpc_request):
        if isinstance(jsonrpc_request.urn.params, list):
            request_params = jsonrpc_request.urn.params[0]
        elif isinstance(jsonrpc_request.urn.params, dict):
            request_params = jsonrpc_request.urn.params['trx']
        else:
            raise ValueError(
                f'Unknown request params type: {type(jsonrpc_request.urn.params)} urn:{jsonrpc_request.urn}')
        ops = [op for op in request_params['operations'] if op[0] == 'custom_json']
        if not ops:
            return
        blacklist_accounts = set()
        try:
            blacklist_accounts = limits['accounts_blacklist']
        except Exception as e:
            logger.warning('using empty accounts_blacklist: %s', e)

        limit_custom_json_op_length(ops, size_limit=CUSTOM_JSON_SIZE_LIMIT)
        limit_custom_json_account(ops, blacklist_accounts=blacklist_accounts)


def limit_custom_json_op_length(ops: list, size_limit=None):
    if any(len(op[1]['json']) > size_limit for op in ops):
        raise JussiCustomJsonOpLengthError(size_limit=size_limit)


def limit_custom_json_account(ops: list, blacklist_accounts=None):
    accts = set(
        it.chain.from_iterable(op[1]["required_posting_auths"] for op in ops))
    if not accts.isdisjoint(blacklist_accounts):
        raise JussiLimitsError()


def block_num_from_id(block_hash: str) -> int:
    """return the first 4 bytes (8 hex digits) of the block ID (the block_num)
    """
    return int(str(block_hash)[:8], base=16)


def jsonrpc_cache_key(single_jsonrpc_request: SingleJsonRpcRequest) -> str:
    return str(single_jsonrpc_request.urn)
