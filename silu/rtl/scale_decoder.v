// Author: Minchan Kwon
// Scale Decoder
// Decodes the FP16 scale input and extracts the exponent, and mantissa bits.
// The output flags invalid, relu, half tell the SiLU unit to force output y = 0,
// approximate with ReLU, and round respectively.

module scale_decoder (
    input  wire [15:0] scale,  // FP16 scale
    output wire [4:0]  exponent,
    output wire [10:0] mantissa,
    output wire        invalid,
    output wire        relu,
    output wire        half
);
    wire [9:0] man_dp = scale[9:0];  // Mantissa decimal point
    assign exponent   = scale[14:10];  // Exponent
    assign mantissa   = {1'b1, man_dp};  // Full mantissa
    assign invalid    = scale[15] | ((exponent == 5'd0) && (man_dp == 10'd0)) 
                        | (exponent == 5'd31);  // Negative | Zero | Inf
    assign relu       = (exponent >= 5'd15);
    assign half       = (exponent <= 5'd1);
endmodule