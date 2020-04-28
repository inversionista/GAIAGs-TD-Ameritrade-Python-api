import os
import time
import json
import datetime
import pathlib
import requests
import urllib.parse
from . import defaults
from typing import Dict
from typing import List
from typing import Optional
from typing import Any
from td.orders import Order
from td.orders import OrderLeg
from td.stream import TDStreamerClient
from td.fields import VALID_CHART_VALUES
from td.fields import ENDPOINT_ARGUMENTS



class TDClient():

    """GAIAGs TD Ameritrade API Client Class.

    Implementación de OAuth 2.0 Codigo de Coutorización Grant workflow, Manejo de Configuración
    y adminsitración de estado, agrega token para llamadas autenticadas y realiza la solicitud 
    a la API de TD Ameritrade.
    """

    def __init__(self, client_id: str, redirect_uri: str, account_number: str = None, credentials_path: str = None) -> None:
        """Crea una nueva instancia del objeto TDClient.
        Inicializa la sesión con valores predeterminados y cualquier anulación proporcionada por el usuario.
        los siguientes argumentos DEBEN especificarse en tiempo de ejecución o, de lo contrario, la inicialización fallará.
        
        Arguments:
        --------
            consumer_id {str} -- La identificación del consumidor que se le asignó durante el registro de la aplicación.
            Esto se puede encontrar en el portal de registro de la aplicación.

            account_number {str} -- Este es el número de cuenta de su cuenta principal
            Cuenta de TD Ameritrade.

            redirect_uri {str} -- Esta es la URL de redireccionamiento que especificó cuando creó su
            Aplicación TD Ameritrade.
            
            credentials_path {str} -- La ruta al archivo de credenciales JSON generado por
            Objeto TDClient.
        """

        # define the configuration settings.
        self.config = {
            'cache_state': True,
            'api_endpoint': 'https://api.tdameritrade.com',
            'api_version': 'v1',
            'auth_endpoint': 'https://auth.tdameritrade.com/auth',
            'token_endpoint': 'oauth2/token',
            'refresh_enabled': True
        }
        
        # define the initalized state, these are the default values.
        self.state = {
            'access_token': None,
            'refresh_token': None,
            'access_token_expires_at': 0,
            'refresh_token_expires_at': 0,
            'authorization_url': None,
            'redirect_code': None,
            'loggedin': False
        }

        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.account_number = account_number
        self.credentials_path = credentials_path
        

        # call the state_manager method and update the state to init (initalized)
        self._state_manager('init')

        # define a new attribute called 'authstate' and initalize it to '' (Blank). This will be used by our login function.
        self.authstate = False

        # Initalize the client with no streaming session.
        self.streaming_session = None

    def __repr__(self) -> str:
        """Representación de cadena de nuestra instancia de clase TD Ameritrade."""

        # define the string representation
        str_representation = '<TDAmeritrade Client (logged_in = {}, authorized = {})>'.format(self.state['loggedin'], self.authstate)

        return str_representation

    def _headers(self, mode: str = None) -> dict:
        """Create the headers for a request.

        Returns a dictionary of default HTTP headers for calls to TD Ameritrade API,
        in the headers we defined the Authorization and access token.

        Arguments:
        --------
            mode {str} -- Defines the content-type for the headers dictionary. (default: {None})
        
        Returns:
        --------
            dict -- Dictionary with the Access token and content-type
            if specified
        """

        # create the headers dictionary
        headers = {'Authorization': 'Bearer {token}'.format(token = self.state['access_token'])}

        if mode == 'json':
            headers['Content-Type'] = 'application/json'
        elif mode == 'form':
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        return headers

    def _api_endpoint(self, endpoint: str, resource: str = None) -> str:
        """Convert relative endpoint (e.g., 'quotes') to full API endpoint.

        Arguments:
        --------
            endpoint {str} -- The URL that needs conversion to a full endpoint URL.

            resource {str} -- The API resource URL that you want to request. (default: {None})

        Returns:
        --------
            str -- A full url that specifies a valid endpoint.
        """

        # Define the parts.
        if resource:
            parts = [resource, self.config['api_version'], endpoint]
        else:
            parts = [self.config['api_endpoint'], self.config['api_version'], endpoint]

        

        # Built the URl
        return '/'.join(parts)

    def _state_manager(self, action: str) -> None:
        """Manages the session state.

        Manages the self.state dictionary. Initalize State will set
        the properties to their default value. Save will save the 
        current state if 'cache_state' is set to TRUE.

        Arguments:
        --------
            action: action argument must of one of the following:
                'init' -- Initalize State.
                'save' -- Save the current state.
        """

        # Grab the current directory of the client file, that way we can store the JSON file in the same folder.
        if self.credentials_path is not None:
            json_session_file = pathlib.Path(self.credentials_path)
            json_session_path = json_session_file.absolute()
        else:
            file_name = 'td_state.json'
            json_file_dir = defaults.default_dir
            if not os.path.isdir(defaults.default_dir): os.makedirs(defaults.default_dir)
            json_session_file = os.path.join(json_file_dir, file_name)
            json_session_file = pathlib.Path(json_session_file)
            # print('file exists: ', json_session_file.exists())
            json_session_path = json_session_file.absolute()

        # if they allow for caching and the file exists then load it.
        if action == 'init' and self.config['cache_state'] == True and json_session_file.exists():
            self.state.update(json.load(open(json_session_path, 'r')))

        # If they don't allow for caching and the file exists, then delete it.
        elif action == 'init' and self.config['cache_state'] == False and json_session_file.exists():
            json_session_file.unlink()

        # if they allow for caching and the file does not exists then use the default state.
        elif action == 'init' and self.config['cache_state'] == True and json_session_file.exists() == False:
            print('Their is no state file to load, will use default state.')

        # if they want to save it and have allowed for caching then load the file.
        elif action == 'save' and self.config['cache_state']:

            # build JSON string using dictionary comprehension.
            json_string = {key: self.state[key] for key in self.state}
            with open(json_session_path, 'w+') as json_file:
                json.dump(json_string, json_file)

    def login(self) -> bool:
        """Registra al usuario en la API de TD Ameritrade.
        Solicite al usuario que se autentique a través del portal de autenticación TD Ameritrade. 
        Esto creará una URL, la mostrará para que el Usuario acceda y solicite que pegue la URL final 
        en la ventana de comandos. Una vez que el usuario se autentica, la clave API es válida durante 
        90 días, por lo que se pueden usar tokens de actualización desde este punto, hasta los 90 días.

        Returns:
        --------
            bool -- Especifica si fue exitoso o no.
        """

        # if caching is enabled then attempt silent authentication.
        if self.config['cache_state'] and self._silent_sso():
            self.authstate = 'Authenticated'
            return True

        # prepare the payload to login
        data = {
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id + '@AMER.OAUTHAP'
        }

        # url encode the data.
        params = urllib.parse.urlencode(data)

        # build the full URL for the authentication endpoint.
        url = self.config['auth_endpoint'] + "/?" + params

        # set the newly created 'authorization_url' key to the newly created url
        self.state['authorization_url'] = url

        # aks the user to go to the URL provided, they will be prompted to authenticate themsevles.
        print('Por favot Vaya a la URL proporcionada y autorice su cuenta: {}'.format(self.state['authorization_url']))

        # ask the user to take the final URL after authentication and paste here so we can parse.
        my_response = input('Pegue la URL completa de redireccionamiento aquí: ')

        # store the redirect URL
        self.state['redirect_code'] = my_response

        # this will complete the final part of the authentication process.
        self.grab_access_token()
        self.authstate = 'Authenticated'

        return True

    def logout(self) -> None:
        """Clears the current TD Ameritrade Connection state."""

        # change state to initalized so they will have to either get a
        # new access token or refresh token next time they use the API
        self._state_manager('init')

    def grab_access_token(self) -> None:
        """Access token handler for AuthCode Workflow.
        
        This takes the authorization code parsed from
        the auth endpoint to call the token endpoint
        and obtain an access token.
        """

        # Parse the URL
        url_dict = urllib.parse.parse_qs(self.state['redirect_code'])

        # Grab the Code.
        url_code = list(url_dict.values())[0][0]

        # Define the parameters of our access token post.
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id + '@AMER.OAUTHAP',
            'access_type': 'offline',
            'code': url_code,
            'redirect_uri': self.redirect_uri
        }

        token_response = self._make_request(
            method='post',
            endpoint=self.config['token_endpoint'],
            mode='form',
            data=data
        )

        self._token_save(token_response)
        self._state_manager('save')
        return True
    
    def grab_refresh_token(self) -> bool:
        """Refreshes the current access token."""

        # build the parameters of our request
        data = {
            'client_id': self.client_id,
            'grant_type': 'refresh_token',
            'access_type': 'offline',
            'refresh_token': self.state['refresh_token']
        }

        token_response = self._make_request(
            method='post',
            endpoint=self.config['token_endpoint'],
            mode='form',
            data=data
        )

        self._token_save(token_response)
        self._state_manager('save')
        return True

    def _silent_sso(self):
        """
            Attempt a silent authentication, by checking whether current access token
            is valid and/or attempting to refresh it. Returns True if we have successfully 
            stored a valid access token.

        Returns:
        --------
            bool -- Specifies whether it was successful or not.
        """

        # if the current access token is not expired then we are still authenticated.
        if self._token_seconds(token_type='access_token') > 0:
            return True

        # if the refresh token is expired then you have to do a full login.
        elif self._token_seconds(token_type='refresh_token') <= 0:
            return False

        # if the current access token is expired then try and refresh access token.
        elif self.state['refresh_token'] and self.grab_refresh_token():
            return True

        # More than likely a first time login, so can't do silent authenticaiton.
        return False

    def _token_save(self, token_dict: dict) -> None:
        """Parses the token and saves it.
        
        Parses an access token from the response of a POST request and saves it
        in the state dictionary for future use. Additionally, it will store the
        expiration time and the refresh token.

        Arguments:
        --------
            token_dict {dict} -- A response object recieved from the `grab_refresh_token` or
                `grab_access_token` methods.
        """

        # make sure there is an access token before proceeding.
        if 'access_token' not in token_dict:
            self.logout()
            return False

        # save the access token and refresh token
        self.state['access_token'] = token_dict['access_token']
        self.state['refresh_token'] = token_dict['refresh_token']

        # store token expiration time
        access_token_expire = time.time() + int(token_dict['expires_in'])
        refresh_token_expire = time.time() + int(token_dict['refresh_token_expires_in'])
        self.state['access_token_expires_at'] = access_token_expire
        self.state['refresh_token_expires_at'] = refresh_token_expire
        self.state['loggedin'] = True

        return True

    def _token_seconds(self, token_type: str = 'access_token') -> int:
        """Determines time till expiration for a token.
        
        Return the number of seconds until the current access token or refresh token
        will expire. The default value is access token because this is the most commonly used
        token during requests.

        Arguments:
        --------
            token_type {str} --  The type of token you would like to determine lifespan for. 
                Possible values are ['access_token', 'refresh_token'] (default: {access_token})
        """

        # if needed check the access token.
        if token_type == 'access_token':

            # if the time to expiration is less than or equal to 0, return 0.
            if not self.state['access_token'] or time.time() >= self.state['access_token_expires_at']:
                return 0

            # else return the number of seconds until expiration.
            token_exp = int(self.state['access_token_expires_at'] - time.time())

        # if needed check the refresh token.
        elif token_type == 'refresh_token':

            # if the time to expiration is less than or equal to 0, return 0.
            if not self.state['refresh_token'] or time.time() >= self.state['refresh_token_expires_at']:
                return 0

            # else return the number of seconds until expiration.
            token_exp = int(self.state['refresh_token_expires_at'] - time.time())

        return token_exp

    def _token_validation(self, nseconds: int = 5):
        """Checks if a token is valid.

        Verify the current access token is valid for at least N seconds, and
        if not then attempt to refresh it. Can be used to assure a valid token
        before making a call to the TD Ameritrade API.

        Arguments:
        --------
            nseconds {int} -- The minimum number of seconds the token has to be 
                valid for before attempting to get a refresh token. (default: {5})
        """

        if self._token_seconds(token_type='access_token') < nseconds and self.config['refresh_enabled']:
            self.grab_refresh_token()


    def _make_request(self, method: str, endpoint: str, mode: str = None, params: dict = None, data: dict = None, json:dict = None, 
                        order_details: bool = False) -> Any:
        """Handles all the requests in the library.

        A central function used to handle all the requests made in the library,
        this function handles building the URL, defining Content-Type, passing
        through payloads, and handling any errors that may arise during the request.

        Arguments:
        --------
            method: The Request method, can be one of the
                following: ['get','post','put','delete','patch']
            
            endpoint: The API URL endpoint, example is 'quotes'

            mode: The content-type mode, can be one of the
                following: ['form','json']
            
            params: The URL params for the request.
            
            data: A data payload for a request.

            json: A json data payload for a request

        Returns:
        --------
            A Dictionary object containing the JSON values.            
        """

        url = self._api_endpoint(endpoint=endpoint)
        headers = self._headers(mode=mode)

        # Make sure the token is valid if it's not a Token API call.
        if endpoint != self.config['token_endpoint']:
            self._token_validation()
        elif endpoint == self.config['token_endpoint']:
            del headers['Authorization']

        # Handle the request.
        if method == 'get':   
            response = requests.get(url=url, headers=headers, params=params, data=data, json=json, verify=True)
        elif method == 'post':            
            response = requests.post(url=url, headers=headers, params=params, data=data, json=json, verify=True)
        elif method == 'put':
            response = requests.put(url=url, headers=headers, params=params, data=data, json=json, verify=True)
        elif method == 'delete':
            response = requests.delete(url=url, headers=headers, params=params, data=data, json=json, verify=True)
        elif method == 'patch':
            response = requests.patch(url=url, headers=headers, params=params, data=data, json=json, verify=True)

        # grab the status code
        status_code = response.status_code

        # grab the response headers.
        response_headers = response.headers

        # Grab the order id, if it exists.
        if 'Location' in response_headers:
            order_id = response_headers['Location'].split('orders/')[1]
        else:
            order_id = ''

        if status_code in (200, 201):

            if order_details:

                response_dict = {
                    'order_id':order_id,
                    'headers':response_headers,
                    'content':response.content,
                    'status_code':status_code,
                    'request_body':response.request.body,
                    'request_method':response.request.method
                }

                return response_dict

            elif response_headers['Content-Type'] in ('application/json;charset=UTF-8','application/json'):
                return response.json()



        elif status_code in (401, 400, 403, 415, 500):
            print('-'*80)
            print("BAD REQUEST - STATUS CODE: {}".format(status_code))
            print("RESPONSE URL: {}".format(response.url))
            print("RESPONSE HEADERS: {}".format(response.headers))
            print("RESPONSE PARAMS: {}".format(response.links))
            print("RESPONSE TEXT: {}".format(response.text))
            print('-'*80)

    def _validate_arguments(self, endpoint: str, parameter_name: str, parameter_argument: List[str]) -> bool:
        """Validates arguments for an API call.

        This will validate an argument for the specified endpoint and raise an error if the argument
        is not valid. Can take both a list of arguments or a single argument.

        Arguments:
        --------
            endpoint: This is the endpoint name, and should line up 
                exactly with the TD Ameritrade Client library.

            parameter_name: An endpoint can have a parameter that needs 
                to be passed through, this represents the name 
                of that parameter.

            parameter_argument: The arguments being validated for the 
                particular parameter name. This can either be a single
                value or a list of values.

        Usage:
        --------
            api_endpoint = 'get_market_hours'
            para_name = 'markets'
            para_args = ['FOREX', 'EQUITY']

            self.validate_arguments(
                endpoint = api_endpoint, 
                parameter_name = para_name, 
                parameter_argument = para_args
            )

        Returns:
        --------
            A boolean specifying whether all the values are valid {True}
        
        Raises:
            ValueError()
        """

        message = '\nThe argument is not valid, please choose a valid argument: {}\n'

        # Grab the parameters, and the possible arguments.
        parameters = ENDPOINT_ARGUMENTS[endpoint]
        arguments = parameters[parameter_name]

        if isinstance(parameter_argument,str):
            parameter_argument = [parameter_argument]

        # See if any of the arguments aren't in the possible values.
        validation_result = [argument in arguments for argument in parameter_argument]

        # if any of the results are FALSE then raise an error.
        if False in validation_result:
            raise ValueError(message.format(' ,'.join(arguments)))
        else:
            return True

    def _prepare_arguments_list(self, parameter_list: List) -> str:
        """Preps an argument list for an API Call.

        Some endpoints can take multiple values for a parameter, this
        method takes that list and creates a valid string that can be 
        used in an API request. The list can have either one index or
        multiple indexes.

        Arguments:
        --------
            parameter_list: A list of paramater values 
                assigned to an argument.

        Usage:
        --------
            SessionObject._prepare_arguments_list(parameter_list = ['MSFT', 'SQ'])
        """

        return ','.join(parameter_list)

    def get_quotes(self, instruments: List) -> Dict:
        """Grabs real-time quotes for an instrument.

        Serves as the mechanism to make a request to the Get Quote and Get Quotes Endpoint.
        If one item is provided a Get Quote request will be made and if more than one item
        is provided then a Get Quotes request will be made.

        Documentation:
        --------
        https://developer.tdameritrade.com/quotes/apis

        Arguments:
        --------
            instruments: A list of different financial instruments.

        Usage:
        --------
            SessionObject.get_quotes(instruments=['MSFT'])
            SessionObject.get_quotes(instruments=['MSFT','SQ'])

        """
        # because we have a list argument, prep it for the request.
        instruments = self._prepare_arguments_list(parameter_list=instruments)

        # build the params dictionary
        params = {
            'apikey': self.client_id,
            'symbol': instruments
        }

        # define the endpoint
        endpoint = 'marketdata/quotes'

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_price_history(self, symbol: str, period_type:str = None, period=None, start_date:str = None, end_date:str = None,
                          frequency_type: str = None, frequency: str = None, extended_hours: bool = True) -> Dict:
        """Gets historical candle data for a financial instrument.
        
        Documentation:
        --------
        https://developer.tdameritrade.com/price-history/apis

        Arguments:
        --------
            symbol: The ticker symbol to request data for. 

            period_type: The type of period to show. 
                Valid values are day, month, year, or 
                ytd (year to date). Default is day.

            period: The number of periods to show.
            
            start_date: Start date as milliseconds
                since epoch.

            end_date: End date as milliseconds
                since epoch.

            frequency_type: The type of frequency with 
                which a new candle is formed.

            frequency: The number of the frequency type 
                to be included in each candle.

            extended_hours: True to return extended hours 
                data, false for regular market hours only.
                Default is true
        """

        # Fail early, can't have a period with start and end date specified.
        if (start_date and end_date and period):
            raise ValueError('Cannot have Period with start date and end date')
        
        # Check only if you don't have a date and do have a period.
        elif (not start_date and not end_date and period):

            # Attempt to grab the key, if it fails we know there is an error.
            try:

                # check if the period is valid.
                if period in VALID_CHART_VALUES[frequency_type][period_type]:
                    True
                else:
                    raise IndexError('Invalid Period.')
            except:
                raise KeyError('Invalid Frequency Type or Period Type you passed through is not valid')

            if frequency_type == 'minute' and frequency not in [1, 5, 10, 15, 30]:
                raise ValueError('Invalid Minute Frequency, must be 1,5,10,15,30')

        # build the params dictionary
        params = {
            'apikey': self.client_id,
            'period': period,
            'periodType': period_type,
            'startDate': start_date,
            'endDate': end_date,
            'frequency': frequency,
            'frequencyType': frequency_type,
            'needExtendedHoursData': extended_hours
        }

        # define the endpoint
        endpoint = 'marketdata/{}/pricehistory'.format(symbol)

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def search_instruments(self, symbol: str, projection: str = None) -> Dict:
        """ Search or retrieve instrument data, including fundamental data.

        Documentation:
        --------
        https://developer.tdameritrade.com/instruments/apis/get/instruments

        Arguments:
        --------
            symbol: The symbol of the financial instrument you would 
                like to search.
            
            projection: The type of request, default is "symbol-search". 
                The type of request include the following:

                  1. symbol-search
                     Retrieve instrument data of a specific symbol or cusip

                  2. symbol-regex
                     Retrieve instrument data for all symbols matching regex. 
                     Example: symbol=XYZ.* will return all symbols beginning with XYZ

                  3. desc-search
                     Retrieve instrument data for instruments whose description contains 
                     the word supplied. Example: symbol=FakeCompany will return all 
                     instruments with FakeCompany in the description

                  4. desc-regex
                     Search description with full regex support. Example: symbol=XYZ.[A-C] 
                     returns all instruments whose descriptions contain a word beginning 
                     with XYZ followed by a character A through C

                  5. fundamental
                     Returns fundamental data for a single instrument specified by exact symbol.

        Usage:
        --------
            SessionObject.search_instrument(symbol = 'XYZ', projection = 'symbol-search')
            SessionObject.search_instrument(symbol = 'XYZ.*', projection = 'symbol-regex')
            SessionObject.search_instrument(symbol = 'FakeCompany', projection = 'desc-search')
            SessionObject.search_instrument(symbol = 'XYZ.[A-C]', projection = 'desc-regex')
            SessionObject.search_instrument(symbol = 'XYZ.[A-C]', projection = 'fundamental')

        """

        # validate argument
        self._validate_arguments(
            endpoint='search_instruments',
            parameter_name='projection', 
            parameter_argument=projection
        )

        # build the params dictionary
        params = {
            'apikey': self.client_id,
            'symbol': symbol,
            'projection': projection
        }

        # define the endpoint
        endpoint = 'instruments'

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_instruments(self, cusip: str) -> Dict:
        """Searches an Instrument.
        
        Get an instrument by CUSIP (Committee on Uniform Securities Identification Procedures) code.

        Documentation:
        --------
        https://developer.tdameritrade.com/instruments/apis/get/instruments/%7Bcusip%7D

        Arguments:
        --------
            cusip: The CUSIP code of a given financial instrument.
        
        Usage:
        --------
            SessionObject.get_instruments(cusip='SomeCUSIPNumber')

        """

        # build the params dictionary
        params = {
            'apikey': self.client_id
        }

        # define the endpoint
        endpoint = 'instruments/{cusip}'.format(cusip=cusip)

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_market_hours(self, markets: List[str], date: str) -> Dict:
        """Returns the hours for a specific market.

        Serves as the mechanism to make a request to the "Get Hours for Multiple Markets" and 
        "Get Hours for Single Markets" Endpoint. If one market is provided a "Get Hours for Single Markets" 
        request will be made and if more than one item is provided then a "Get Hours for Multiple Markets" 
        request will be made.

        Documentation:
        --------
        https://developer.tdameritrade.com/market-hours/apis
        
        Arguments:
        --------
            markets: The markets for which you're requesting market hours, 
                comma-separated. Valid markets are:
                EQUITY, OPTION, FUTURE, BOND, or FOREX.

            date: The date you wish to recieve market hours for. 
                Valid ISO-8601 formats are: yyyy-MM-dd and yyyy-MM-dd'T'HH:mm:ssz

        Usage:
        --------
            SessionObject.get_market_hours(markets = ['EQUITY'], date = '2019-10-19')
            SessionObject.get_market_hours(markets = ['EQUITY','FOREX'], date = '2019-10-19')

        """

        # validate argument
        self._validate_arguments(
            endpoint='get_market_hours',
            parameter_name='markets', 
            parameter_argument=markets
        )

        # because we have a list argument, prep it for the request.
        markets = self._prepare_arguments_list(parameter_list=markets)

        # build the params dictionary
        params = {
            'apikey': self.client_id,
            'markets': markets,
            'date': date
        }

        # define the endpoint
        endpoint = 'marketdata/hours'

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_movers(self, market: str, direction: str, change: str) -> Dict:
        """Gets Active movers for a specific Index.
        
        Top 10 (up or down) movers by value or percent for a particular market.
        Documentation:
        --------
        https://developer.tdameritrade.com/movers/apis/get/marketdata

        Arguments:
        --------
            market The index symbol to get movers for. 
                Can be $DJI, $COMPX, or $SPX.X.

            direction: To return movers with the specified 
                directions of up or down. Valid values are `up`
                or `down`

            change: To return movers with the specified change 
                types of percent or value. Valid values are `percent`
                or `value`.   

        Usage:
        --------
            SessionObject.get_movers(market='$DJI', direction='up', change='value')
            SessionObject.get_movers(market='$COMPX', direction='down', change='percent')
        """

        # grabs a dictionary representation of our arguments and their inputs.
        local_args = locals()

        # we don't need the 'self' key
        del local_args['self']

        # validate arguments, before making request.
        for key, value in local_args.items():
            self._validate_arguments(
                endpoint='get_movers', 
                parameter_name=key, 
                parameter_argument=value
            )

        # build the params dictionary
        params = {
            'apikey': self.client_id,
            'direction': direction,
            'change': change
        }

        # define the endpoint
        endpoint = 'marketdata/{market_id}/movers'.format(market_id=market)

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_options_chain(self, option_chain: Dict) -> Dict:
        """Returns Option Chain Data and Quotes.

        Get option chain for an optionable Symbol using one of two methods. Either,
        use the OptionChain object which is a built-in object that allows for easy creation of the
        POST request. Otherwise, can pass through a dictionary of all the arguments needed.

        Documentation:
        --------
        https://developer.tdameritrade.com/option-chains/apis/get/marketdata/chains

        Arguments:
        --------
            option_chain: Represents a dicitonary containing values to
                query.

        Usage:
        --------
            SessionObject.get_options_chain(option_chain={'key1':'value1'})
        """

        # define the endpoint
        endpoint = 'marketdata/chains'

        # otherwise take the args dictionary.
        params = option_chain

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    """
    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------
    
        THIS BEGINS THE ACCOUNTS ENDPOINTS PORTION.

    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------
    """

    def get_accounts(self, account: str = 'all', fields: List[str] = None) -> Dict:
        """Queries accounts for a user.

        Serves as the mechanism to make a request to the "Get Accounts" and "Get Account" Endpoint. 
        If one account is provided a "Get Account" request will be made and if more than one account 
        is provided then a "Get Accounts" request will be made.

        Documentation:
        -------- 
        https://developer.tdameritrade.com/account-access/apis

        Arguments:
        --------
            account {str} -- The account number you wish to recieve data on. Default value is 'all'
                  which will return all accounts of the user.

            fields {List[str]} -- Balances displayed by default, additional fields can be added here by 
                  adding positions or orders.

        Usage:
        --------
            SessionObject.get_accounts(account='all', fields=['orders'])
            SessionObject.get_accounts(account='MyAccountNumber', fields=['orders','positions'])

        """

        # because we have a list argument, prep it for the request.
        if fields:
            fields = self._prepare_arguments_list(parameter_list=fields)

        # build the params dictionary
        params = {
            'apikey': self.client_id,
            'fields': fields
        }

        # if all use '/accounts' else pass through the account number.
        if account == 'all':
            endpoint = 'accounts'
        else:
            endpoint = 'accounts/{}'.format(account)

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)


    def get_transactions(self, account: str = None, transaction_type: str = None, symbol: str = None,
                         start_date: str = None, end_date: str = None, transaction_id: str= None) -> Dict:
        """Queries the transactions for an account.
    
        Serves as the mechanism to make a request to the "Get Transactions" and "Get Transaction" Endpoint. 
        If one `transaction_id` is provided a "Get Transaction" request will be made and if it is not provided
        then a "Get Transactions" request will be made.

        Documentation:
        --------
        https://developer.tdameritrade.com/transaction-history/apis

        Arguments:
        --------

            account {str} -- The account number you wish to recieve
            transactions for.

            transaction_type: The type of transaction. Only 
                transactions with the specified type will be returned. 
                Valid values are the following:
                    1. ALL
                    2. TRADE
                    3. BUY_ONLY
                    4. SELL_ONLY
                    5. CASH_IN_OR_CASH_OUT
                    6. CHECKING
                    7. DIVIDEND
                    8. INTEREST
                    9. OTHER
                    10. ADVISOR_FEES

            symbol The symbol in the specified transaction. Only transactions
                with the specified symbol will be returned.

            start_date: Only transactions after the Start Date will be returned. 
                Note: The maximum date range is one year. Valid ISO-8601 
                formats are: yyyy-MM-dd.

            end_date: Only transactions before the End Date will be returned. 
                Note: The maximum date range is one year. Valid ISO-8601 
                formats are: yyyy-MM-dd.

            transaction_id: The transaction ID you wish to search. If this is 
                specifed a "Get Transaction" request is made. Should only be
                used if you wish to return one transaction.

        Usage:
        --------
            SessionObject.get_transactions(account = 'MyAccountNumber', transaction_type = 'ALL', start_date = '2019-01-31', end_date = '2019-04-28')
            SessionObject.get_transactions(account = 'MyAccountNumber', transaction_type = 'ALL', start_date = '2019-01-31')
            SessionObject.get_transactions(account = 'MyAccountNumber', transaction_type = 'TRADE')
            SessionObject.get_transactions(transaction_id = 'MyTransactionID')

        """

        # default to a "Get Transaction" Request if anything else is passed through along with the transaction_id.
        if transaction_id != None:
            account = None
            transaction_type = None,
            start_date = None,
            end_date = None

        # if the request type they made isn't valid print an error and return nothing.
        else:

            if transaction_type not in ['ALL', 'TRADE', 'BUY_ONLY', 'SELL_ONLY', 'CASH_IN_OR_CASH_OUT', 'CHECKING', 'DIVIDEND', 'INTEREST', 'OTHER', 'ADVISOR_FEES']:
                print('The type of transaction type you specified is not valid.')
                raise ValueError('Bad Input')

        # if transaction_id is not none, it means we need to make a request to the get_transaction endpoint.
        if transaction_id:

            # define the endpoint
            endpoint = 'accounts/{}/transactions/{}'.format(account, transaction_id)

            # return the response of the get request.
            return self._make_request(method='get', endpoint=endpoint)

        # if it isn't then we need to make a request to the get_transactions endpoint.
        else:

            # build the params dictionary
            params = {
                'type': transaction_type,
                'symbol': symbol,
                'startDate': start_date,
                'endDate': end_date
            }

            # define the endpoint
            endpoint = '/accounts/{}/transactions'.format(account)

            # return the response of the get request.
            return self._make_request(method='get', endpoint=endpoint, params=params)

    """
    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------
    
        THIS BEGINS THE USER INFOS & PREFERENCES ENDPOINTS PORTION.

    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------
    """

    def get_preferences(self, account: str) -> Dict:
        """Get's User Preferences for a specific account.

        Documentation:
        --------
        https://developer.tdameritrade.com/user-principal/apis/get/accounts/%7BaccountId%7D/preferences-0

        Arguments:
        --------
            account {str} -- The account number you wish to 
                recieve preference data for.

        Usage:
        --------
            SessionObject.get_preferences(account='MyAccountNumber')
        
        Returns:
        --------
            Perferences dictionary
        """

        # define the endpoint
        endpoint = 'accounts/{}/preferences'.format(account)

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint)

    def get_streamer_subscription_keys(self, accounts: List[str]) -> Dict:
        """SubscriptionKey for provided accounts or default accounts.

        Documentation:
        --------
        https://developer.tdameritrade.com/user-principal/apis/get/userprincipals/streamersubscriptionkeys-0

        Arguments:
        --------
            account:A list of account numbers you wish to recieve a 
                streamer key for.

        Usage:
        --------
            SessionObject.get_streamer_subscription_keys(account = ['MyAccountNumber'])
            SessionObject.get_streamer_subscription_keys(account = ['MyAccountNumber1', 'MyAccountNumber2'])
        """


        # because we have a list argument, prep it for the request.
        accounts = self._prepare_arguments_list(parameter_list=accounts)

        # define the endpoint
        endpoint = 'userprincipals/streamersubscriptionkeys'

        # build the params dictionary
        params = {
            'accountIds': accounts
        }

        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_user_principals(self, fields: List[str]) -> Dict:
        """Returns User Principal details.

        Documentation:
        --------
        https://developer.tdameritrade.com/user-principal/apis/get/userprincipals-0

        Arguments:
        --------

            fields: A comma separated String which allows one to specify additional fields to return. None of 
                these fields are returned by default. Possible values in this String can be:
                    1. streamerSubscriptionKeys
                    2. streamerConnectionInfo
                    3. preferences
                    4. surrogateIds

        Usage:
        --------
            SessionObject.get_user_principals(fields = ['preferences'])
            SessionObject.get_user_principals(fields = ['preferences', 'streamerConnectionInfo'])
        """

        # validate arguments
        self._validate_arguments(
            endpoint='get_user_principals',
            parameter_name='fields', 
            parameter_argument=fields
        )

        # because we have a list argument, prep it for the request.
        fields = self._prepare_arguments_list(parameter_list=fields)

        # define the endpoint
        endpoint = 'userprincipals'

        # build the params dictionary
        params = {
            'fields': fields
        }


        # return the response of the get request.
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def update_preferences(self, account: str, data_payload: Dict) -> Dict:
        """Update User Preferences

        Update preferences for a specific account. Please note that the directOptionsRouting and 
        directEquityRouting values cannot be modified via this operation.

        Documentation:
        --------
        https://developer.tdameritrade.com/user-principal/apis/put/accounts/%7BaccountId%7D/preferences-0

        Arguments:
        --------        

            account: The account number you wish to update preferences for.

            data_payload: A dictionary that provides all the keys you wish to update. 
                It must contain the following keys to be valid.

                  1. expressTrading
                  2. directOptionsRouting
                  3. directEquityRouting
                  4. defaultEquityOrderLegInstruction
                  5. defaultEquityOrderType
                  6. defaultEquityOrderPriceLinkType
                  7. defaultEquityOrderDuration
                  8. defaultEquityOrderMarketSession
                  9. defaultEquityQuantity
                  10. mutualFundTaxLotMethod
                  11. optionTaxLotMethod
                  12. equityTaxLotMethod
                  13. defaultAdvancedToolLaunch
                  14. authTokenTimeout
        
        Usage:
        --------
            SessionObject.update_preferences(account = 'MyAccountNumer', dataPayload = <Dictionary>)

        """

        # define the endpoint
        endpoint = 'accounts/{}/preferences'.format(account)

        # make the request
        return self._make_request(method='put', endpoint=endpoint, mode='json', data=data_payload)

    """
    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------
    
        THIS BEGINS THE WATCHLISTS ENDPOINTS PORTION.

    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------
    """

    def create_watchlist(self, account: str, name: str, watchlistItems=None) -> Dict:
        """Creates a new watchlist.

        Create watchlist for specific account. This method does not verify that the 
        symbol or asset type are valid.

        Documentation:
        --------
        https://developer.tdameritrade.com/watchlist/apis/post/accounts/%7BaccountId%7D/watchlists-0

        Arguments:
        --------        

            account: The account number you wish to create the watchlist for.

            name: The name you want to give your watchlist.

            watchlistItems: A list of WatchListItems object.

        Usage:
        --------

            WatchListItem1 = WatchListItem()
            WatchListItem2 = WatchListItem()

            SessionObject.create_watchlist(account = 'MyAccountNumber', 
                                           name = 'MyWatchlistName', 
                                           watchlistItems = [ WatchListItem1, WatchListItem2 ])

        """

        # define the endpoint
        endpoint = 'accounts/{}/watchlists'.format(account)

        # define the payload
        payload = {
            "name": name,
            "watchlistItems": watchlistItems
        }

        # make the request
        return self._make_request(method='put', endpoint=endpoint, mode='json', data=payload)

    def get_watchlist_accounts(self, account: str = 'all') -> Dict:
        """
            Serves as the mechanism to make a request to the "Get Watchlist for Single Account" and 
            "Get Watchlist for Multiple Accounts" Endpoint. If one account is provided a 
            "Get Watchlist for Single Account" request will be made and if 'all' is provided then a 
            "Get Watchlist for Multiple Accounts" request will be made.

        Documentation:
        --------
        https://developer.tdameritrade.com/watchlist/apis

        Arguments:
        --------

            account: The account number you wish to pull watchlists from. Default value is 'all'

        Usage:
        --------

            SessionObject.get_watchlist_accounts(account = 'all')
            SessionObject.get_watchlist_accounts(account = 'MyAccount1')

        """

        # define the endpoint
        if account == 'all':
            endpoint = 'accounts/watchlists'
        else:
            endpoint = 'accounts/{}/watchlists'.format(account)

        # make the request
        return self._make_request(method='get', endpoint=endpoint)

    def get_watchlist(self, account: str, watchlist_id: str) -> Dict:
        """Queries a watchlist.
        
        Returns a specific watchlist for a specific account designated by the
        watchlist ID.

        Documentation:
        --------
        https://developer.tdameritrade.com/watchlist/apis/get/accounts/%7BaccountId%7D/watchlists/%7BwatchlistId%7D-0

        Arguments:
        --------

            account:The account number you wish to pull watchlists from.

            watchlist_id: The ID of the watchlist you wish to return.

        Usage:
        --------

            SessionObject.get_watchlist(account = 'MyAccount1', watchlist_id = 'MyWatchlistId')

        """

        # define the endpoint
        endpoint = 'accounts/{}/watchlists/{}'.format(account, watchlist_id)

        # make the request
        return self._make_request(method='get', endpoint=endpoint)

    def delete_watchlist(self, account: str, watchlist_id: str) -> Dict:
        """Deletes an existing watchlist

        Deletes a specific watchlist for a specific account.

        Documentation:
        --------
        https://developer.tdameritrade.com/watchlist/apis/delete/accounts/%7BaccountId%7D/watchlists/%7BwatchlistId%7D-0

        Arguments:
        --------

            account: The account number you wish to delete the watchlist from.

            watchlist_id: The ID of the watchlist you wish to delete.

        Usage:
        --------

            SessionObject.delete_watchlist(account = 'MyAccount1', watchlist_id = 'MyWatchlistId')

        """


        # define the endpoint
        endpoint = 'accounts/{}/watchlists/{}'.format(account, watchlist_id)

        # make the request
        return self._make_request(method='delete', endpoint=endpoint)

    def update_watchlist(self, account: str, watchlist_id: str, name: str, watchlistItems: Dict) -> Dict:
        """Updates an Exisitng watchlist.

            Partially update watchlist for a specific account: change watchlist name, add to the beginning/end of a 
            watchlist, update or delete items in a watchlist. This method does not verify that the symbol or asset 
            type are valid.

        Documentation:
        -------- 
        https://developer.tdameritrade.com/watchlist/apis/patch/accounts/%7BaccountId%7D/watchlists/%7BwatchlistId%7D-0

        Arguments:
        --------

            account: The account number that contains the watchlist you wish to update.

            watchlist_id: The ID of the watchlist you wish to update.

            watchlistItems: A list of the original watchlist items you wish to update and their modified keys.
         
        Usage:
        --------

            WatchListItem1 = WatchListItem()
            WatchListItem2 = WatchListItem()

            SessionObject.update_watchlist(
                account = 'MyAccountNumber', 
                watchlist_id = 'WatchListID', 
                watchlistItems = [WatchListItem1, WatchListItem2]
            )

        """

        # define the payload
        payload = {
            "name": name,
            "watchlistItems": watchlistItems
        }

        # define the endpoint
        endpoint = 'accounts/{}/watchlists/{}'.format(account, watchlist_id)

        # make the request
        return self._make_request(method='patch', endpoint=endpoint, data=payload)

    def replace_watchlist(self, account: str, watchlist_id_new: dict, watchlist_id_old: dict, name_new: str, watchlistItems_new: dict) -> Dict:
        """Replaces an existing watchlist.
            
        Replace watchlist for a specific account. This method does not verify that 
        the symbol or asset type are valid.

        Documentation:
        -------- 
        https://developer.tdameritrade.com/watchlist/apis/put/accounts/%7BaccountId%7D/watchlists/%7BwatchlistId%7D-0

            account: The account number that contains the watchlist you wish to replace.

            watchlist_id_new: The ID of the watchlist you wish to replace with the old one.

            watchlist_id_old: The ID of the watchlist you wish to replace.

            name_new The name: of the new watchlist.

            watchlistItems_New: The new watchlist items you wish to add to the watchlist.
         
        Usage:
        --------

            WatchListItem1 = WatchListItem()
            WatchListItem2 = WatchListItem()

            SessionObject.replace_watchlist(
                account = 'MyAccountNumber', 
                watchlist_id_new = 'WatchListIDNew', 
                watchlist_id_old = 'WatchListIDOld', 
                name_new = 'MyNewName', 
                watchlistItems_new = [ WatchListItem1, WatchListItem2 ]
            )

        """

        # define the payload
        payload = {
            "name": name_new,
            "watchlistId": watchlist_id_new,
            "watchlistItems": watchlistItems_new
        }

        # define the endpoint
        endpoint = 'accounts/{}/watchlists/{}'.format(account, watchlist_id_old)

        # make the request
        return self._make_request(method='put', endpoint=endpoint, mode='json', data=payload)

    """
    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------

        THIS BEGINS THE ORDERS ENDPOINTS PORTION.

    ---------------------------------------------------------------------------------------------------------------
    ---------------------------------------------------------------------------------------------------------------
    """

    def get_orders_path(self, account: str, max_results: int = None, from_entered_time: 
                            str = None, to_entered_time: str = None, status: str = None) -> Dict:
        """Returns the orders for a specific account.

        Documentation:
        -------- 
            https://developer.tdameritrade.com/account-access/apis/get/accounts/%7BaccountId%7D/orders-0

        Arguments:
        --------
            account: The account number that you want to query for orders.

            max_results: The maximum number of orders to retrieve.

            from_entered_time: Specifies that no orders entered before this time should be returned. Valid ISO-8601 formats are:
                yyyy-MM-dd and yyyy-MM-dd'T'HH:mm:ssz Date must be within 60 days from today's date. 'to_entered_time' 
                must also be set.

            to_entered_time: Specifies that no orders entered after this time should be returned.Valid ISO-8601 formats are:
                yyyy-MM-dd and yyyy-MM-dd'T'HH:mm:ssz. 'from_entered_time' must also be set.

            status: Specifies that only orders of this status should be returned. 
                Possible Values are:

                    1. AWAITING_PARENT_ORDER
                    2. AWAITING_CONDITION
                    3. AWAITING_MANUAL_REVIEW
                    4. ACCEPTED
                    5. AWAITING_UR_NOT
                    6. PENDING_ACTIVATION
                    7. QUEDED
                    8. WORKING
                    9. REJECTED
                    10. PENDING_CANCEL
                    11. CANCELED
                    12. PENDING_REPLACE
                    13. REPLACED
                    14. FILLED
                    15. EXPIRED

        Usage:
        --------
            SessionObject.get_orders_query(account = 'MyAccountID', max_results = 6, from_entered_time = '2019-10-01', to_entered_time = '2019-10-10', status = 'FILLED')
            SessionObject.get_orders_query(account = 'MyAccountID', max_results = 6, status = 'EXPIRED')
            SessionObject.get_orders_query(account = 'MyAccountID', status = 'REJECTED')
            SessionObject.get_orders_query(account = 'MyAccountID')

        """

        # define the payload
        params = {
            "maxResults": max_results, 
            "fromEnteredTime": from_entered_time,
            "toEnteredTime": to_entered_time,
            "status": status
        }

        # define the endpoint
        endpoint = 'accounts/{}/orders'.format(account)

        # make the request
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_orders_query(self, account: str = None, max_results: int = None, from_entered_time: str = None, 
                            to_entered_time: str = None, status: str = None) -> Dict:
        """Get's all the orders for an account.

        All orders for a specific account or, if account ID isn't specified, orders will be returned for all linked accounts

        Documentation:
        --------
        https://developer.tdameritrade.com/account-access/apis/get/orders-0

        Arguments:
        --------

            account:The account number that you want to query for orders, or if none provided will query all.

            max_results: The maximum number of orders to retrieve.

            from_entered_time: Specifies that no orders entered before this time should be returned. Valid ISO-8601 formats are:
                yyyy-MM-dd and yyyy-MM-dd'T'HH:mm:ssz Date must be within 60 days from today's date. 'to_entered_time' 
                must also be set.

            to_entered_time: Specifies that no orders entered after this time should be returned.Valid ISO-8601 formats are:
                yyyy-MM-dd and yyyy-MM-dd'T'HH:mm:ssz. 'from_entered_time' must also be set.

            status: Specifies that only orders of this status should be returned.
                Possible Values are:

                  1. AWAITING_PARENT_ORDER
                  2. AWAITING_CONDITION
                  3. AWAITING_MANUAL_REVIEW
                  4. ACCEPTED
                  5. AWAITING_UR_NOT
                  6. PENDING_ACTIVATION
                  7. QUEDED
                  8. WORKING
                  9. REJECTED
                  10. PENDING_CANCEL
                  11. CANCELED
                  12. PENDING_REPLACE
                  13. REPLACED
                  14. FILLED
                  15. EXPIRED
                  
        Usage:
        --------

            SessionObject.get_orders_query(account = 'MyAccountID', max_results = 6, from_entered_time = '2019-10-01', to_entered_time = '2019-10-10', status = 'FILLED')
            SessionObject.get_orders_query(account = 'MyAccountID', max_results = 6, status = 'EXPIRED')
            SessionObject.get_orders_query(account = 'MyAccountID', status = 'REJECTED')
            SessionObject.get_orders_query(account =  None)

        """

        # define the payload
        params = {
            "accountId": account,
            "maxResults": max_results,
            "fromEnteredTime": from_entered_time,
            "toEnteredTime": to_entered_time,
            "status": status
        }

        # define the endpoint
        endpoint = 'orders'

        # make the request
        return self._make_request(method='get', endpoint=endpoint, params=params)

    def get_orders(self, account: str, order_id: str = None) -> Dict:
        """Gets the orders for an account

        Returns all orders for a specific account or, if account ID 
        isn't specified, orders will be returned for all linked
        accounts.

        Documentation:
        --------
        https://developer.tdameritrade.com/account-access/apis/get/orders-0
        
        Arguments:
        --------
            account {str} -- The account number that you want to query orders for.
        
        Keyword Arguments:
        --------
            order_id {str} -- The ID of the order you want to delete. (default: {None})
        
        Usage:
        --------
            SessionObject.get_order(account='MyAccountID', order_id='MyOrderID')
        
        Returns:
        --------
            Dict -- A response dicitonary.
        """
        

        # define the endpoint
        if order_id:
            endpoint = 'accounts/{}/orders/{}'.format(account, order_id)
        else:
            endpoint = 'accounts/{}/orders'.format(account)

        # make the request
        return self._make_request(method='get', endpoint=endpoint)

    def cancel_order(self, account: str, order_id: str) -> Dict:
        """Cancel a specific order for a specific account.

        Documentation:
        --------
        https://developer.tdameritrade.com/account-access/apis/delete/accounts/%7BaccountId%7D/orders/%7BorderId%7D-0

        Arguments:
        --------
            account {str} -- The account number that the order was made for.

            order_id {str} -- The ID of the order you want to delete.

        Usage:
        --------
            SessionObject.cancel_order(account='MyAccountID', order_id='MyOrderID')
        
        Returns:
        --------
            A response dicitonary.
        """

        # define the endpoint
        endpoint = 'accounts/{}/orders/{}'.format(account, order_id)

        # delete the request
        return self._make_request(method='delete', endpoint=endpoint, order_details=True)


    def place_order(self, account: str, order: dict) -> dict:
        """Places an order for a specific account.

        Documentation:
        --------
        https://developer.tdameritrade.com/account-access/apis/delete/accounts/%7BaccountId%7D/orders/%7BorderId%7D-0

        Arguments:
        --------
            account {str} -- The account number that you want to place the order for.

            order {dict} -- The order payload.

        Usage:
        --------
            SessionObject.place_order(account='MyAccountID', order={'orderKey':'OrderValue'})
        
        Returns:
        --------
            A response dicitonary.
        """

        # check to see if it's an order object.
        if isinstance(order, Order):
            order = order._saved_order_to_json()
        else:
            order = order

        # make the request
        endpoint = 'accounts/{}/orders'.format(account)
        return self._make_request(method='post', endpoint=endpoint, mode='json', json=order, order_details=True)
    
    def modify_order(self, account: str, order: dict, order_id: str) -> dict:
        """Modifies an exisiting order.

        Documentation:
        --------
        https://developer.tdameritrade.com/account-access/apis/delete/accounts/%7BaccountId%7D/orders/%7BorderId%7D-0

        Arguments:
        --------
            account {str} -- The account number that the order was place for.

            order {dict} -- The new order payload.

            order_id {str} -- The ID of the exisitng order.

        Usage:
        --------
            SessionObject.place_order(account='MyAccountID', order={'orderKey':'OrderValue'})
        
        Returns:
        --------
            A response dicitonary.
        """
        # make the request
        endpoint = 'accounts/{account_id}/orders/{order_id}'.format(account_id=account, order_id=order_id)
        return self._make_request(method='put', endpoint=endpoint, mode='json', json=order, order_details=True)

    def get_saved_order(self, account: str, saved_order_id: str = None) -> Dict:
        """Grabs a saved order.

        Grabs all the saved orders for a specific account or, if account 
        ID isn't specified, orders will be returned for all linked accounts
        Documentation:
        -------- 
        https://developer.tdameritrade.com/account-access/apis/get/orders-0

        Arguments:
        --------
            account {str} -- The account number that you want to place the order for.

            saved_order_id {str} --  The saved order id.
        
        Usage:
        --------
            SessionObject.get_order(account='MyAccountID', saved_order_id='MyOrderID')

        Returns:
        --------
            Saved Order Dictionary.            
        """

        # define the endpoint
        endpoint = 'accounts/{}/savedorders/{}'.format(account, saved_order_id)
        return self._make_request(method='get', endpoint=endpoint)

    def cancel_saved_order(self, account: str, saved_order_id: str) -> Dict:
        """Cancel a saved order 
        
        Using a saved order ID and account number, will delete the order from
        the specified account.      
        Documentation:
        -------- 
        https://developer.tdameritrade.com/account-access/apis/delete/accounts/%7BaccountId%7D/orders/%7BorderId%7D-0

        Arguments:
        --------
            account {str} -- The account number that you want to place the order for.

            saved_order_id {str} --  The saved order id.
        
        Usage:
        --------
            SessionObject.cancel_order(account = 'MyAccountID', saved_order_id = 'MyOrderID')

        Returns:
        --------
            Order response dictionary.
        """

        # define the endpoint
        endpoint = 'accounts/{}/savedorders/{}'.format(account, saved_order_id)
        return self._make_request(method='delete', endpoint=endpoint, order_details=True)


    def create_saved_order(self, account: str, saved_order: dict) -> dict:
        """Creates a saved order

        Creates a saved order for the specified account.

        Documentation:
        -------- 
        https://developer.tdameritrade.com/account-access/apis/delete/accounts/%7BaccountId%7D/orders/%7BorderId%7D-0

        Arguments:
        --------
            account {str} -- The account number that you want to place the order for.

            saved_order {dict} -- The order payload.

        Usage:
        --------
            SessionObject.place_order(account = 'MyAccountID', saved_order = {'orderKey':'OrderValue'})
        
        Returns:
        --------
            A response dicitonary.
        """

        # check to see if it's an order object.
        if isinstance(saved_order, Order):
            order = order._saved_order_to_json()
        else:
            order = order

        # make the request
        endpoint = 'accounts/{}/savedorders'.format(account)
        return self._make_request(method='post', endpoint=endpoint, mode='json', data=order, order_details=True)

    def _create_token_timestamp(self, token_timestamp: str) -> int:
        """Parses the token and converts it to a timestamp.
        
        Arguments:
        --------
            token_timestamp {str} -- The timestamp returned from the get_user_principals endpoint.
        
        Returns:
        --------
            int -- the token timestamp as an integer.
        """

        token_timestamp = datetime.datetime.strptime(token_timestamp, "%Y-%m-%dT%H:%M:%S%z")
        token_timestamp = int(token_timestamp.timestamp()) * 1000

        return token_timestamp

    def create_streaming_session(self) -> TDStreamerClient:
        """Creates a new streaming session with the TD API.

        Grab the token to authenticate a stream session, builds
        the credentials payload, and initalizes a new instance
        of the TDStream client.

        Returns:
        --------
            TDStreamerClient
        """
        
        # Grab the Streamer Info.
        userPrincipalsResponse = self.get_user_principals(
            fields=['streamerConnectionInfo','streamerSubscriptionKeys','preferences','surrogateIds'])


        # Grab the timestampe.
        tokenTimeStamp = userPrincipalsResponse['streamerInfo']['tokenTimestamp']

        # Grab socket
        socket_url = userPrincipalsResponse['streamerInfo']['streamerSocketUrl']

        # Parse the token timestamp.
        tokenTimeStampAsMs = self._create_token_timestamp(
            token_timestamp=tokenTimeStamp)

        # Define our Credentials Dictionary used for authentication.
        credentials = {
            "userid": userPrincipalsResponse['accounts'][0]['accountId'],
            "token": userPrincipalsResponse['streamerInfo']['token'],
            "company": userPrincipalsResponse['accounts'][0]['company'],
            "segment": userPrincipalsResponse['accounts'][0]['segment'],
            "cddomain": userPrincipalsResponse['accounts'][0]['accountCdDomainId'],
            "usergroup": userPrincipalsResponse['streamerInfo']['userGroup'],
            "accesslevel": userPrincipalsResponse['streamerInfo']['accessLevel'],
            "authorized": "Y",
            "timestamp": tokenTimeStampAsMs,
            "appid": userPrincipalsResponse['streamerInfo']['appId'],
            "acl": userPrincipalsResponse['streamerInfo']['acl']
        }

        # Create the session
        streaming_session = TDStreamerClient(
            websocket_url=socket_url,
            user_principal_data=userPrincipalsResponse, 
            credentials=credentials
        )

        return streaming_session