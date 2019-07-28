<?php
	
	function restGET($URI)
	{
		$szUsername = "username";
		$szPassword = "password";
		$aOpts = array('http' => array('method' => "GET",'header' => "Authorization: Basic ".base64_encode("$szUsername:$szPassword")));
		$context = stream_context_create($aOpts);
		$szJSON = file_get_contents($URI, false, $context);
		$result = json_decode($szJSON, true);
		return ($result);
	}
	
	function getHeaders($env, $request)
	{
		$stack = array();
		if ($request = restGET($request)) {
			$membersCount = count($request['member']);
			for ($index = 0; $index < $membersCount; $index++) {
				foreach($request['member'][$index] as $key => $item){
					if (!in_array($key,$stack))
						array_push($stack, $key);
				}
			}
		}
		return ($stack);
	}

	function printTableFirstLine($headers)
	{
		echo('<table class="table table-bordered" width="100%" cellspacing="0" style="font-size: 75%;">'.PHP_EOL);
		echo('<tr id="env-table-header" class="thead-light">'.PHP_EOL);		
		foreach ($headers as $header)
			echo('<th class="card-heading">'.$header.'</th>'.PHP_EOL);
		echo('</tr>'.PHP_EOL);
		echo('</table>'.PHP_EOL);
	}
?>