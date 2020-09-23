#
#   EXTERNAL LIBARIES
#
# Purpose loggging
import logging
# Enables logging with the logging module
log = logging.getLogger(__name__)
# Tells the logging module to ignore all logging message, if a program using this file does not use the logging module.
log.addHandler(logging.NullHandler())

# Purpose: CLI
import argparse

# Terminate program on exception
import sys

# Purpose: Math
import numpy as np

# Hanlde file paths
import pathlib

# Get time and date for output file
from datetime import datetime

#
#   INTERNAL MODULES
#
import SetupDecoder as SetDec
import utilities as util

#
# MAIN PROGRAM
#
def main(cliArgs):
    """
    Function will be called by the subcommand 'run' and runs the main program: the mueller simulation
    """
    log.info("START MUELLER SIMULATION")
    log.info("Instruction File: " + str(cliArgs.inputfile) )

    # Read input file
    labratory_setup = util.readFileAsText(cliArgs.inputfile).splitlines()

    log.info("Matrix File: " + str(cliArgs.matrixfile.resolve()) )
    # Read matrices from file
    # Result is a list of dictionaries containing the matrices and descriptive headers
    sampleMatrix = util.readFileAsMatrices(cliArgs.matrixfile)

    # Make sure the matrix file is not the default matrix file containing just a unit matrix
    if cliArgs.matrixfile == pathlib.Path("unitmatrix.txt"):
        log.critical("WARNING: No matrix file specified. SMP will act as NOP!")

# INITIALISE SIMULATION

    # Declare one stokes vector for every raman matrix
    # Include the header information of sampleMatrix in state values
    initialState = [ { "head": matrix["head"], "state": np.array([0, 0, 0, 0]) } for matrix in sampleMatrix ]
    currentState = [ { "head": matrix["head"], "state": np.array([0, 0, 0, 0]) } for matrix in sampleMatrix ]

    # Get instruction decoder
    decoder = SetDec.SetupDecoder()

# RUN SIMULATION

    # Decode instructions and calculate simulation
    for step, encodedInstruction in enumerate(labratory_setup, 1):

        # Print info about progress
        log.info("Simulation Step: " + str(step) + "    Instruction: " + encodedInstruction)

        # Decode encoded into mueller matrix or stokes vector
        decodedInstruction = decoder.decode(encodedInstruction)

        # Check if instruction is a new stokes vector or a mueller matrix to multiply or the raman matrix of the sample to multiply
        if isinstance(decodedInstruction, np.ndarray) and decodedInstruction.ndim == 1:
            # LSR command detected
            # Reinitialsise the state of the simulation
            currentState = [ { "head": state["head"], "state": decodedInstruction } for state in currentState ]
            initialState = [ { "head": state["head"], "state": decodedInstruction } for state in initialState ]

        elif isinstance(decodedInstruction, np.ndarray) and decodedInstruction.ndim == 2:
            # Mueller matrix of optical element detected
            # Alter stokes vector with the mueller matrix
            currentState = [ { "head": state["head"], "state": decodedInstruction @ state["state"] } for state in currentState ]

        elif decodedInstruction == "SMP":
            # SMP command detected

            log.info("Convert raman tensor to mueller formalism.")
            for index, (state, tensor) in enumerate( zip(currentState, sampleMatrix) ):

                if state["head"] == tensor["head"]:
                    # The stokes vector will only be changed if the header of the mueller matrix and the header of the stokes vector match

                    # Convert the raman tensor into a mueller matrix
                    matrix = util.buildRamanMuellerMatrix( tensor["matrix"] )

                    # Make sure the conversion formula for the raman tensor does apply
                    log.info("Check state vector '" + state["head"] + "'.")
                    # Make sure the polarisation grade is 1
                    polarisation = np.sqrt(state["state"][1]**2 + state["state"][2]**2 + state["state"][3]**2) / state["state"][0]
                    polarisation = round( polarisation , 7)
                    if np.not_equal(polarisation, 1):
                        log.error("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. Polarisation grade is " + str(polarisation) + ". Must be equal to one for SMP instruction!")
                        raise ValueError("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. Polarisation grade is " + str(polarisation) + ". Must be equal to one for SMP instruction!")
                    # Make sure there is no circular polarisation
                    if round( state["state"][3], 7 ) != 0:
                        log.error("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. The SMP instruction can't handle circular polarisation!")
                        raise ValueError("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. The SMP instruction can't handle circular polarisation!")

                    log.info("Apply raman mueller matrix to state vector.")
                    # Apply mueller matrix to current state of the simulation
                    currentState[index] = { "head": state["head"], "state": matrix @ state["state"] }

                else:
                    # Raise an exception if headers don't match
                    log.critical("INTERNAL ERROR: The headers of the samples raman tensor and the current state of the simulation don't match.")
                    raise ValueError("INTERNAL ERROR: The headers of the samples raman tensor and the current state of the simulation don't match.")

        else:
            # Handle unexpected behaviour
            log.critical("INTERNAL ERROR: Unexprected mueller matrix! '" + encodedInstruction + "' in line " + str(step) + " can't be executed. Exiting execution.")
            sys.exit(-1)

        # Log current state of simulation
        log.info("State of Simulation")
        logstring = str( np.array([ state["state"] for i, state in enumerate(currentState) ]) ).replace("[[", "").replace(" [", "").replace("]", "").splitlines()
        for index, state in enumerate(currentState):
            log.info("[ " + logstring[index] + " ] " + str(state["head"]))

        # Make sure there was no light circular polarised during the simulation
        # Make sure the computed stokes vector is physical possible
        log.info("Check validity of simulation step.")
        for state in currentState:
            # Make sure that the polarisation grade is not greater than one
            # Rounding to avoid exceptions due to floating point errors
            polarisation = np.sqrt(state["state"][1]**2 + state["state"][2]**2 + state["state"][3]**2) / state["state"][0]
            polarisation = round( polarisation , 7)
            if np.greater(polarisation, 1):
                log.error("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. Polarisation grade is " + str(polarisation) + ". Can't be greater than one!")
                raise ValueError("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. Polarisation grade greater than one is not possible!")

            # Make sure that the light intensity is not smaller than zero
            elif state["state"][0] < 0:
                log.error("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. The total light intensity can't be negative!")
                raise ValueError("SIMULATION ERROR: Error in state vector '" + state["head"] + "'. The total light intensity can't be negative!")

# PRINT RESULTS TO FILE
    output_text = "# polaram simulate " + str(cliArgs.inputfile.resolve()) + " --output " + str(cliArgs.outputfile.resolve()) + " --log " + str(cliArgs.logfile.resolve()) + " --matrix " + str(cliArgs.matrixfile.resolve()) + "\n# Execution time: " + str(datetime.now()) + "\n"

    # Add user comment to string
    if cliArgs.comment != "":
        output_text += "\n# " + str(cliArgs.comment) + "\n"

    # Add labratory_setup to string
    output_text += "\n# Simulation Program:\n" + "\n".join(labratory_setup) + "\n"

    # Add the calculated states to the string.
    output_text += "\n# Simulation Results:"
    formattedTable = str( np.array([ state["state"] for i, state in enumerate(currentState) ]) ).replace("[[", "").replace(" [", "").replace("]", "").splitlines()
    for index, vector in enumerate(formattedTable):
        output_text += "\n[" + vector + " ] " + currentState[index]["head"]

    # Log and write text to file
    log.debug("Writing results to '" + str(cliArgs.outputfile.resolve()) + "':\n\n" + output_text + "\n")
    print(output_text)
    cliArgs.outputfile.write_text(output_text)

    log.info("STOPPED MUELLER SIMULATION SUCCESSFULLY")
