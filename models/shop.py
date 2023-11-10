class Shop:
    def __init__(self, name, location, phone_number, debtors=None):
        self.name = name
        self.location = location
        self.phone_number = phone_number
        self.debtors = debtors if debtors is not None else []

    def to_dict(self):
        return {
            'name': self.name,
            'location': self.location,
            'phone_number': self.phone_number,
            'debtors': self.debtors
        }
