#define WLED 2
#define REDLED 3
#define IRLED 4
#define SENSOR A0

char buf[10];

void get_reading(int *ir, int *red) {
    PORTD = (PORTD | _BV(PD3));
    *ir = analogRead(A0);
    PORTD = PORTD ^ (_BV(PD3) | _BV(PD4));
    *red = analogRead(A0);
    PORTD = PORTD & ~(_BV(PD3) | _BV(PD4));
}

void setup() {
    Serial.begin(115200);
    pinMode(SENSOR, INPUT);
    pinMode(REDLED, OUTPUT);
    pinMode(IRLED, OUTPUT);
    pinMode(WLED, OUTPUT);
    digitalWrite(WLED, HIGH);
}

void loop() {
    int ir, red;
    while(Serial.available() == 0) {}
    while(Serial.available() > 0) {
        Serial.read();
    }
    get_reading(&ir, &red);
    sprintf(buf, "$%03d,%03d\n", ir, red);
    Serial.print(buf);
}
