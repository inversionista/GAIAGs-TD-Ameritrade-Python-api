import json

class WatchlistItem():

    '''
        TD Ameritrade API WatchlistItem Class.

         Implementa la creación y validación de solicitudes de elementos de la lista de observación. Estas
         El tipo de solicitudes puede tomar múltiples argumentos posibles, requiere información para ser
         anidado, y solo acepta una cadena JSON pura.

         Esta clase ayudará al usuario a construir, validar y modificar las solicitudes realizadas a este punto final.
    '''

    def __init__(self, **kwargs):
        '''
            Inicializa el objeto WatchListItem y anula cualquier valor predeterminado que sea
             pasado a través.
        '''

        # argument types used for validation.
        self.argument_types = {
            'assetType':  ['EQUITY', 'OPTION', 'MUTUAL_FUND', 'FIXED_INCOME', 'INDEX']
        }

        # the possible parameters that can be set during initalization for a watchlist item.
        self.query_parameters = {
            'quantity': 0,
            'averagePrice': 0.00,
            'commission': 0.00,
            'purchasedDate': None,
            'symbol': None,
            'assetType': None
        }

        # THIS WILL BE A TWO STEP VALIDATION
        # Step One: Make sure none of the kwargs are invalid. No sense of trying to validate an incorrect argument.
        for key in kwargs:
            if key not in self.query_parameters:
                print("WARNING: The argument, {} is an unkown argument.".format(key))
                raise KeyError('Invalid Argument Name.')

        # Step Two: Validate the argument values, if good then update query parameters.
        if self.validate_watchlist(keyword_args=kwargs):
            self.query_parameters.update(kwargs.items())

    def validate_watchlist(self, keyword_args=None):
        '''
            Un elemento de la lista de observación solo puede tener valores de especificación especificados, si esos valores no se especifican
             entonces pueden ocurrir errores. Este método validará los argumentos pasados durante la inicialización
             y genera un error si alguno de los valores es incorrecto.

             La lista de observación es relativamente simple de validar porque el único argumento que tenemos que verificar es
             el `assetType`. Sin embargo, se pueden agregar protocolos de validación adicionales en el futuro, por lo que está hecho
             mas general.

             NOMBRE: keyword_args
             DESC: Un diccionario de argumentos de palabras clave proporcionado durante la inicialización.
             TIPO: Diccionario

             RTYPE booleano
        '''

        # grab the items, if you find a key that needs validation, then compare to the list of possible values.
        for key, value in keyword_args.items():
            if (key in self.argument_types.keys()) and (value not in self.argument_types[key]):
                print('\nFor the "{}" argument you specified "{}", this is an invalid value. Please use one of the following value values: {} \n'.format(
                    key, value, ', '.join(self.argument_types[key])))
                raise KeyError('Invalid Value.')

        return True

    def create_watchlist_json(self):
        '''
            Una solicitud de lista de observación es propensa a errores porque requiere construir una cadena JSON anidada. Esta
             El método automatizará ese proceso y garantizará que cada vez que desee enviar una solicitud esté en
             El formato correcto. Además, convertirá el objeto del diccionario en una cadena JSON.


             Edwin Notas
             ----------

             REQUIERE MÁS VALIDACIÓN, NO PODRÍA NECESITAR JSON STRING.

             Siento que esto se puede simplificar, no me gusta tener que eliminar claves. Tal vez ver si
             ¿Puede modificar el proceso de inicialización para que ya esté anidado?

             Además, podría tener sentido agregar una segunda ronda de validación en caso de que el usuario haya modificado un valor.
             Haga algo similar a la clase OptionChain que permita al usuario llamar a un método que modificará
             argumentos?


             RTYPE: String
        '''

        # grab the current arguments
        current_params = self.query_parameters

        # create the nested dictionary.
        instrument_dict = {
            'symbol': current_params['symbol'], 'assetType': current_params['assetType']}

        # delete the old values.
        del current_params['symbol']
        del current_params['assetType']

        # add the nested dict to the newly created `instrument` key.
        current_params['instrument'] = instrument_dict

        # make JSON string
        json_string = json.dumps(current_params)

        return json_string
